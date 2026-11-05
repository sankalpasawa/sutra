"""The operator commands (gaps G08/G09): `sutra-pro doctor | status | stop | config show|set|init|sync-library | open`.

    sutra-pro [serve] [flags]     the server, unchanged: no subcommand means serve (`sutra_app.main.run`)
    sutra-pro <command> ...       one of the commands below; each takes --data-dir and --json

Exit codes: 0 fine, 1 a problem was found (a failed check, nothing running, a refusal), 2 usage (a bad flag, a bad value, a bad setting).

More commands arrive from other packages: GAP-DATA's modules (`sutra_app.ops.backup`, `retention`, `exporter`) offer `register(sub)`,
which adds parsers to the `subparsers` action with `sub.add_parser(name, parents=[common_parser()])` and `parser.set_defaults(func=f)`,
where `f(args) -> int`. Modules that do not exist are skipped. `COMMANDS` maps every command name to its `f` once `build_parser()` ran.
`before_start(settings)` calls the optional `sutra_app.ops.backup.before_upgrade(settings)` before the server is built.
"""
import argparse
import importlib
import json
import os
from sutra_app import oslayer
import signal
import sys
import time
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from sutra_app.config import ENV_NAMES, Settings, SettingsError

__all__ = ["main", "dispatch", "build_parser", "common_parser", "COMMANDS", "BUILTIN", "OPTIONAL_MODULES", "load_settings", "emit",
           "before_start", "first_run_problems", "command_names", "STOP_WAIT_S"]

BUILTIN = ("doctor", "status", "stop", "config", "open")
OPTIONAL_MODULES = ("backup", "retention", "exporter")
STOP_WAIT_S = 20.0                       # the app's own stop ladder takes 12 s at most
COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {}


# ---- helpers ------------------------------------------------------------------------------------------------------------------

def common_parser() -> argparse.ArgumentParser:
    """The flags every command takes (a `parents=` parser)."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--data-dir", type=Path, metavar="D", help="the data folder (default: SUTRA_DATA_DIR, else the usual place)")
    parent.add_argument("--json", action="store_true", help="print one JSON document instead of text")
    return parent


def load_settings(args: argparse.Namespace) -> Settings | None:
    """The settings for a command, or None after printing why they cannot be used (the caller returns 2)."""
    try:
        return Settings.load(data_dir=getattr(args, "data_dir", None))
    except SettingsError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return None


def emit(args: argparse.Namespace, payload: dict[str, Any], lines: Sequence[str]) -> None:
    """The command's result: JSON when `--json`, else the text lines."""
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
    else:
        for line in lines:
            print(line)


def _health(port: int, timeout: float = 2.0) -> dict[str, Any] | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=timeout) as response:
            body = json.load(response)
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def _age(seconds: float) -> str:
    seconds = int(max(0, seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days:
        return f"{days} d {hours} h"
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min {secs} s" if minutes else f"{secs} s"


# ---- doctor, status, stop, open -----------------------------------------------------------------------------------------------

def cmd_doctor(args: argparse.Namespace) -> int:
    from sutra_app.ops import doctor
    settings = load_settings(args)
    if settings is None:
        return 2
    report = doctor.run(settings, offline=bool(args.offline or settings.offline or settings.connector == "stub"))
    emit(args, report.to_dict(), report.lines())
    return 0 if report.ok else 1


def cmd_status(args: argparse.Namespace) -> int:
    from sutra_app.ops import lock
    settings = load_settings(args)
    if settings is None:
        return 2
    data_dir = settings.data_dir
    running = lock.is_locked(data_dir)
    holder = lock.read_holder(data_dir) if running else None
    payload: dict[str, Any] = {"running": running, "data_dir": str(data_dir), "pid": None, "port": None, "url": None, "version": None,
                               "started": None, "uptime_s": None, "health": None}
    if not running:
        emit(args, payload, [f"Sutra Pro is not running (data folder {data_dir})."])
        return 1
    lines = []
    code = 0
    if holder is not None:
        payload.update(pid=holder.pid, port=holder.port, url=holder.url, version=holder.version, started=holder.started)
        if holder.started:
            payload["uptime_s"] = round(time.time() - holder.started)
        if holder.port:
            payload["health"] = _health(holder.port)
            if payload["health"] is None:
                code = 1
    where = holder.url if holder is not None and holder.url else "(starting; the port is not known yet)"
    lines.append(f"Sutra Pro is running on {where}" + (f" (pid {holder.pid}" + (f", up {_age(payload['uptime_s'])}" if payload["uptime_s"] is not None else "")
                                                       + (f", version {holder.version}" if holder.version else "") + ")" if holder else ""))
    lines.append(f"  data folder: {data_dir}")
    health = payload["health"]
    if health is not None:
        lines.append(f"  health: {'ok' if health.get('ok') else 'NOT ok'}, schema {health.get('schema')}")
        for name, info in sorted((health.get("connectors") or {}).items()):
            if isinstance(info, dict):
                state = "signed in" if info.get("signed_in") else "not signed in" if info.get("signed_in") is False else "unknown"
                lines.append(f"  {name}: {'installed' if info.get('installed') else 'missing'}, {state}")
        if not health.get("ok"):
            code = 1
    elif holder is not None and holder.port:
        lines.append("  /api/health did not answer within 2 s (still starting, or stuck)")
    emit(args, payload, lines)
    return code


def cmd_stop(args: argparse.Namespace) -> int:
    from sutra_app.ops import lock
    settings = load_settings(args)
    if settings is None:
        return 2
    data_dir = settings.data_dir
    payload: dict[str, Any] = {"was_running": False, "stopped": True, "pid": None}
    if not lock.is_locked(data_dir):
        emit(args, payload, ["Sutra Pro is not running."])
        return 0
    payload["was_running"], payload["stopped"] = True, False
    holder = lock.read_holder(data_dir)
    if holder is None:
        emit(args, payload, [f"Something holds {data_dir} but app.pid does not say what; stop it by hand."])
        return 1
    payload["pid"] = holder.pid
    if oslayer.IS_WINDOWS:
        # a server with no console cannot be signalled (and os.kill would end it on the spot): ask through the file it polls
        try:
            lock.request_stop(data_dir)
        except OSError as exc:
            emit(args, payload, [f"could not ask pid {holder.pid} to stop: {exc.strerror or exc}"])
            return 1
    else:
        try:
            os.kill(holder.pid, signal.SIGTERM)
        except ProcessLookupError:
            emit(args, payload, [f"app.pid names pid {holder.pid}, which is gone, yet the data folder is still locked; not touching anything."])
            return 1
        except PermissionError:
            emit(args, payload, [f"pid {holder.pid} belongs to another user; it was not signalled."])
            return 1
    if not getattr(args, "json", False):
        print(f"Stopping Sutra Pro (pid {holder.pid}); it can take up to 12 s to end its teams cleanly...", flush=True)
    deadline = time.monotonic() + args.wait
    while time.monotonic() < deadline:
        if not lock.is_locked(data_dir):
            payload["stopped"] = True
            emit(args, payload, ["Stopped."])
            return 0
        time.sleep(0.1)
    emit(args, payload, [f"Sutra Pro (pid {holder.pid}) was asked to stop and is still shutting down after {args.wait:g} s. "
                         "It is NOT being killed; run `sutra-pro stop` again in a moment."])
    return 1


def cmd_open(args: argparse.Namespace) -> int:
    from sutra_app.ops import browser, lock
    settings = load_settings(args)
    if settings is None:
        return 2
    holder = lock.read_holder(settings.data_dir) if lock.is_locked(settings.data_dir) else None
    if holder is None or not holder.url:
        emit(args, {"opened": False, "url": None}, ["Sutra Pro is not running. Start it with `sutra-pro`."])
        return 1
    result = browser.open_url(holder.url, args.browser)
    emit(args, {"opened": result.opened, "url": holder.url, "how": result.how, "detail": result.detail},
         [f"Opened {holder.url} ({result.detail})." if result.opened else f"Could not open a browser ({result.detail}); open {holder.url} yourself."])
    return 0 if result.opened else 1


# ---- config -------------------------------------------------------------------------------------------------------------------

def _engine_view(settings: Settings, dept: str | None) -> dict[str, Any]:
    from sutra_app.engine.spec import ENV_NAMES as J2_NAMES, LOCKED_FIELDS, EngineSettings, read_settings_file
    global_file = read_settings_file(settings.data_dir / "engine.json") or {}
    dept_file = read_settings_file(settings.departments_dir / dept / "engine.json") if dept else None
    effective = EngineSettings.layered(os.environ, global_file, dept_file, {})
    fields = {}
    for name in EngineSettings.model_fields:
        if dept_file and name in dept_file:
            source = f"department {dept} engine.json"
        elif (os.environ.get(J2_NAMES[name]) or "").strip():
            source = f"environment ({J2_NAMES[name]})"
        elif name in global_file:
            source = "engine.json"
        else:
            source = "default"
        fields[name] = {"value": getattr(effective, name), "source": source, "locked": name in LOCKED_FIELDS}
    return fields


def _config_show(args: argparse.Namespace, settings: Settings) -> int:
    from sutra_app.engine.spec import SettingsError as EngineSettingsError, read_settings_file
    app = {}
    for key, value in settings.public().items():
        name = ENV_NAMES.get(key)
        app[key] = {"value": value, "source": f"environment ({name})" if name and os.environ.get(name) is not None else "default or flag"}
    try:
        engine = _engine_view(settings, args.dept)
        overrides = {}
        departments = settings.departments_dir
        for path in sorted(departments.glob("*/engine.json")) if departments.is_dir() else []:
            overrides[path.parent.name] = read_settings_file(path)
    except EngineSettingsError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 1
    payload = {"app": app, "env_file": str(settings.env_file), "override_key_set": settings.override_key is not None,
               "engine": {"scope": args.dept or "global", "fields": engine}, "department_overrides": overrides}
    lines = ["App settings (SUTRA_* environment variables and flags):"]
    lines += [f"  {k} = {v['value']}  [{v['source']}]" for k, v in app.items()]
    lines.append(f"  env file = {settings.env_file}  [override key {'set' if settings.override_key is not None else 'not set'}; the key is never printed]")
    lines.append(f"Engine settings, {'department ' + args.dept if args.dept else 'global'} "
                 "(defaults < engine.json < J2_* environment < department engine.json):")
    lines += [f"  {k} = {json.dumps(v['value'])}  [{v['source']}]" + ("  (locked: only `config set` changes it)" if v["locked"] else "")
              for k, v in engine.items()]
    if overrides:
        lines.append("Department files:")
        lines += [f"  {dept}: {json.dumps(values)}" for dept, values in overrides.items()]
    emit(args, payload, lines)
    return 0


def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, (json.dumps(document, indent=2) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    oslayer.replace(tmp, path)


def _config_set(args: argparse.Namespace, settings: Settings) -> int:
    from sutra_app.engine.spec import ENV_NAMES as J2_NAMES, EngineSettings, SettingsError as EngineSettingsError, is_dept_id, read_settings_file
    if args.field not in EngineSettings.model_fields:
        print(f"sutra-pro: unknown engine setting {args.field!r}; the settings are: {', '.join(EngineSettings.model_fields)}", file=sys.stderr)
        return 2
    try:
        value = getattr(EngineSettings.layered({J2_NAMES[args.field]: args.value}, None, None, {}), args.field)
    except EngineSettingsError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 2
    if args.dept is not None:
        if not is_dept_id(args.dept) or not settings.department_dir(args.dept).is_dir():
            print(f"sutra-pro: there is no department folder {args.dept!r} in {settings.departments_dir}", file=sys.stderr)
            return 1
        path = settings.department_dir(args.dept) / "engine.json"
    else:
        path = settings.data_dir / "engine.json"
    try:
        current = read_settings_file(path) or {}
        document = {**current, args.field: value}
        EngineSettings.layered({}, document if args.dept is None else None, document if args.dept is not None else None, {})
    except EngineSettingsError as exc:
        print(f"sutra-pro: {exc}", file=sys.stderr)
        return 1
    _write_json_atomic(path, document)
    lines = [f"{args.field} = {json.dumps(value)} written to {path}; it applies to the next run."]
    if args.field == "send_mode" and value == "live":
        lines.append(f"Live sends need the J2_SMTP_* lines in {settings.env_file}; `sutra-pro doctor` checks them.")
    emit(args, {"field": args.field, "value": value, "file": str(path)}, lines)
    return 0


def _config_init(args: argparse.Namespace, settings: Settings) -> int:
    from sutra_app.ops import envfile
    path = settings.env_file
    try:
        envfile.create(path, generate_override_key=args.generate_override_key)
    except FileExistsError:
        print(f"sutra-pro: {path} already exists and is not overwritten; edit it, or move it away first.", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"sutra-pro: cannot write {path}: {exc.strerror or exc}", file=sys.stderr)
        return 1
    lines = [f"Wrote {path} (mode 600)."]
    if args.generate_override_key:
        lines.append("A new J2_OVERRIDE_KEY is in the file; it is not printed here.")
    else:
        lines.append("Edit it to add the owner override key and the SMTP login, or run with --generate-override-key on a new file.")
    emit(args, {"file": str(path), "override_key_generated": bool(args.generate_override_key)}, lines)
    return 0


def _config_sync(args: argparse.Namespace, settings: Settings) -> int:
    from sutra_app.ops import doctor
    try:
        added = doctor.sync_seed_library(settings.data_dir)
    except OSError as exc:
        print(f"sutra-pro: the library could not be synced: {exc}", file=sys.stderr)
        return 1
    emit(args, {"added": added}, [f"Added {len(added)} template(s): " + ", ".join(added) if added else "The library already has every seed template."])
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    settings = load_settings(args)
    if settings is None:
        return 2
    return {"show": _config_show, "set": _config_set, "init": _config_init, "sync-library": _config_sync}[args.config_cmd](args, settings)


# ---- the parser ---------------------------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sutra-pro", description="Sutra Pro operator commands. `sutra-pro [serve] [flags]` starts the server.")
    sub = parser.add_subparsers(dest="command", metavar="command")
    common = [common_parser()]
    p = sub.add_parser("doctor", parents=common, help="check the machine, the data folder and the setup (14 checks, fix hints)")
    p.add_argument("--offline", action="store_true", help="skip the CLI and browser checks")
    p.set_defaults(func=cmd_doctor)
    sub.add_parser("status", parents=common, help="is it running, where, and is it healthy").set_defaults(func=cmd_status)
    p = sub.add_parser("stop", parents=common, help="ask the running server to stop (SIGTERM, never SIGKILL)")
    p.add_argument("--wait", type=float, default=STOP_WAIT_S, metavar="S", help=f"seconds to wait for it to end (default {STOP_WAIT_S:g})")
    p.set_defaults(func=cmd_stop)
    p = sub.add_parser("open", parents=common, help="open the running app in the browser")
    p.add_argument("--browser", choices=("auto", "chrome", "default"), default="auto", help="auto/chrome: Chrome when installed; default: the system default")
    p.set_defaults(func=cmd_open)
    p = sub.add_parser("config", help="show or change settings, write the .env template, sync the template library")
    cfg = p.add_subparsers(dest="config_cmd", metavar="show|set|init|sync-library", required=True)
    q = cfg.add_parser("show", parents=common, help="the effective settings and where each value comes from")
    q.add_argument("--dept", metavar="D", help="show the engine settings as department D sees them")
    q = cfg.add_parser("set", parents=common, help="set one engine setting (the only way to set a locked one)")
    q.add_argument("field", help="an engine setting, e.g. budget or send_mode")
    q.add_argument("value", help="the new value")
    q.add_argument("--dept", metavar="D", help="write it into this department's engine.json instead of the global one")
    q = cfg.add_parser("init", parents=common, help="write a commented .env template (mode 600); never overwrites")
    q.add_argument("--generate-override-key", action="store_true", help="also put a fresh J2_OVERRIDE_KEY in it")
    cfg.add_parser("sync-library", parents=common, help="copy seed templates the data library lacks (never overwrites)")
    p.set_defaults(func=cmd_config)
    COMMANDS.clear()
    COMMANDS.update({name: sub.choices[name].get_default("func") for name in BUILTIN})
    for module_name in OPTIONAL_MODULES:
        full = f"sutra_app.ops.{module_name}"
        try:
            module = importlib.import_module(full)
        except ModuleNotFoundError as exc:
            if exc.name == full:
                continue
            raise
        register = getattr(module, "register", None)
        if callable(register):
            before = set(sub.choices)
            register(sub)
            for name in set(sub.choices) - before:
                COMMANDS[name] = sub.choices[name].get_default("func")
    return parser


def command_names() -> list[str]:
    """Every command name, the optional ones included (for the `--help` of the server)."""
    build_parser()
    return ["serve", *COMMANDS]


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command. An argparse error (usage) exits 2 through `SystemExit`, as `--help` exits 0."""
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help(sys.stderr)
        return 2
    return int(func(args))


def dispatch(argv: Sequence[str] | None = None) -> int:
    """`sutra-pro`: no argument or a leading flag is the server; `serve` is the server by name; any other word is a command."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "serve":
        args = args[1:]
    elif args and not args[0].startswith("-"):
        return main(args)
    from sutra_app.main import run
    return run(args)


# ---- what the server calls before it starts ---------------------------------------------------------------------------------------

def before_start(settings: Settings) -> None:
    """GAP-DATA's pre-upgrade backup, when that module exists. An exception stops the start (the caller prints it)."""
    full = "sutra_app.ops.backup"
    try:
        module = importlib.import_module(full)
    except ModuleNotFoundError as exc:
        if exc.name == full:
            return
        raise
    hook = getattr(module, "before_upgrade", None)
    if callable(hook):
        hook(settings)


def first_run_problems(settings: Settings) -> list[str]:
    """The failed doctor checks as lines, for the first start on an empty data folder. Never raises: a broken doctor must not stop the app."""
    from sutra_app.ops import doctor
    try:
        report = doctor.run(settings, offline=bool(settings.offline or settings.connector == "stub"))
    except Exception as exc:                                                # noqa: BLE001
        return [f"the doctor could not run ({type(exc).__name__}: {str(exc)[:120]})"]
    return [c.line() for c in report.failures()]
