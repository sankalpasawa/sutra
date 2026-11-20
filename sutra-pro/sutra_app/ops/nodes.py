"""`sutra-pro nodes status | pause | kill | resume`: the owner's switch for multi-agent nodes, by hand (guardrails 7; D279).

    sutra-pro nodes status [--json]            the switch (none, pause or kill), the two files, and the four SUTRA_NODES_* settings
    sutra-pro nodes pause [--reason TEXT]      put the PAUSE file in <data>/nodes: no new agent starts; the ones that run finish
    sutra-pro nodes kill [--reason TEXT]       put the KILL file there: a running Sutra stops every agent through its stop ladder (all together, about 12 seconds at most) and none starts
    sutra-pro nodes resume                     remove both files

The command only writes and removes the two small files (it does not need the server, and it has no token to give one: a launch token is never written to disk). A running Sutra with
SUTRA_NODES_V1=1 looks for the KILL file every two seconds and runs the stop ladder; with it off nothing looks, and the command says so. A file left behind holds the agents back
if the feature is turned on later, which is the safe way round. Exit codes: 0 done, 2 a bad setting.
"""
import argparse
import sys
from typing import Any

from sutra_app.config import Settings
from sutra_app.ops.cli import common_parser, emit, load_settings

__all__ = ["register"]

REASON_MAX = 200               # the longest reason the switch files keep (killswitch.REASON_MAX; the orchestrator is imported only when a command runs, so `sutra-pro --help` stays light)


def _flags(settings: Settings) -> dict[str, bool]:
    return {"SUTRA_NODES_V1": settings.nodes_v1, "SUTRA_NODES_LANES": settings.nodes_lanes, "SUTRA_NODES_REVIEWER": settings.nodes_reviewer, "SUTRA_NODES_SLOTS": settings.nodes_slots}


def _running(settings: Settings) -> dict[str, Any]:
    """What a RUNNING Sutra on this data folder says about itself (D384). The settings of this shell are not the app's: an app opened from the Dock or started elsewhere has its own. So: is a Sutra holding
    the folder, and what does it answer at `/api/nodes/status` (404: projects are switched off in it; 200: they are on, with the settings it was started with). Reads only; one local request."""
    from sutra_app.ops import lock
    try:
        held = lock.is_locked(settings.data_dir)
    except OSError:
        held = False
    if not held:
        return {"state": "not_running"}
    holder = lock.read_holder(settings.data_dir)
    out: dict[str, Any] = {"state": "running", "pid": holder.pid if holder is not None else None, "projects": None}
    if holder is None or not holder.port:
        return out
    import json
    import urllib.error
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{holder.port}/api/nodes/status", timeout=2) as reply:
            body = json.loads(reply.read().decode("utf-8", "replace"))
        out.update(projects=True, level=body.get("level"), settings=body.get("settings") if isinstance(body.get("settings"), dict) else None)
    except urllib.error.HTTPError as exc:
        out["projects"] = False if exc.code == 404 else None
    except (OSError, ValueError):
        out["projects"] = None
    return out


def _running_words(running: dict[str, Any]) -> list[str]:
    if running["state"] == "not_running":
        return ["running Sutra: none holds this folder now. The two files act on the next one that starts with SUTRA_NODES_V1=1."]
    who = f"pid {running['pid']}" if running.get("pid") else "a Sutra"
    if running.get("projects") is True:
        shown = running.get("settings") or {}
        return [f"running Sutra ({who}): projects are ON. " + (", ".join(f"{name}={int(bool(value))}" for name, value in shown.items()) if shown else ""),]
    if running.get("projects") is False:
        return [f"running Sutra ({who}): projects are OFF (it was started without SUTRA_NODES_V1=1), so it does not look at these files and no agent runs."]
    return [f"running Sutra ({who}): it did not answer, so its settings are not known."]


def _off_note(settings: Settings, running: dict[str, Any] | None = None) -> list[str]:
    if running is not None and running["state"] == "running":
        return []
    return [] if settings.nodes_v1 else ["Note: SUTRA_NODES_V1 is 0 in this shell. A Sutra started from here would not look at these files; one started with it on does. They hold agents back if it is turned on later."]


def _status(args: argparse.Namespace) -> int:
    settings = load_settings(args)
    if settings is None:
        return 2
    from sutra_app.orchestrator.killswitch import KillSwitch
    state = KillSwitch(settings.nodes_dir, consume=False).status()
    running = _running(settings)
    payload: dict[str, Any] = {**state, "folder": str(settings.nodes_dir), "settings": _flags(settings), "running": running}
    words = {"none": "Agents may start.", "pause": "The PAUSE file is there: no new agent starts; the ones that run finish.", "kill": "The KILL file is there: a running Sutra stops every agent and starts none. (Look at the page or the log to see that they ended.)"}[state["level"]]
    lines = [f"nodes: {words}", f"  files in {settings.nodes_dir}: KILL {'present' if state['kill'] is not None else 'absent'}, PAUSE {'present' if state['pause'] is not None else 'absent'}"]
    for name in ("kill", "pause"):
        note = state[name]
        if note:
            lines.append(f"  {name.upper()}: " + "; ".join(f"{key} {note[key]}" for key in ("by", "reason", "at") if note.get(key)))
    lines.append("  settings in this shell: " + ", ".join(f"{name}={int(value)}" for name, value in _flags(settings).items()) + " (a running Sutra has its own, below)")
    lines += [f"  {line}" for line in _running_words(running)]
    lines += [f"  {line}" for line in _off_note(settings, running)]
    emit(args, payload, lines)
    return 0


def _write(level: str):
    def run(args: argparse.Namespace) -> int:
        settings = load_settings(args)
        if settings is None:
            return 2
        reason = " ".join((args.reason or "").split())[:REASON_MAX]
        from sutra_app.orchestrator.killswitch import KillSwitch, resume_command
        try:
            KillSwitch(settings.nodes_dir, consume=False).set(level, by="owner", reason=reason)
        except OSError as exc:
            print(f"sutra-pro: could not write the {level.upper()} file in {settings.nodes_dir} ({type(exc).__name__}): nothing is held back", file=sys.stderr)
            return 1
        done = ("Paused: no new agent starts; the ones that run finish." if level == "pause" else
                "Kill switch on: a running Sutra stops every agent (all together, about 12 seconds at most), and none starts.")
        running = _running(settings)
        emit(args, {"level": level, "folder": str(settings.nodes_dir), "running": running}, [done, f"Run `{resume_command(settings.data_dir)}` to remove it.", *_running_words(running), *_off_note(settings, running)])
        return 0
    return run


def _resume(args: argparse.Namespace) -> int:
    settings = load_settings(args)
    if settings is None:
        return 2
    from sutra_app.orchestrator.killswitch import KillSwitch
    switch = KillSwitch(settings.nodes_dir, consume=False)
    if switch.broken():                                       # a plain error, never a silent "killed for ever" (m11)
        emit(args, {"error": "not_a_folder", "path": str(settings.nodes_dir)}, [f"{settings.nodes_dir} is a file, not a folder, so the stop switch cannot work. Rename or remove that file, then run this again."])
        return 1
    removed = switch.clear()
    try:                                                      # tell a running app to let go of a switch it holds in memory (its file could not be written), and what was removed: it writes the audit row (D384)
        with open(switch.resume_marker(), "a", encoding="utf-8") as marker:          # appended: two resumes before the app looks are two rows (D391)
            marker.write("resume\n" + (f"removed: {', '.join(removed)}\n" if removed else ""))
    except OSError:
        pass
    emit(args, {"removed": removed}, ["Resumed: " + ", ".join(removed) + " removed." if removed else "Nothing to resume: neither file was there."])
    return 0


def register(sub: Any) -> None:
    """Add the `nodes` command to the parser (`cli.build_parser` calls this for every optional module)."""
    common = [common_parser()]
    p = sub.add_parser("nodes", help="the switch for multi-agent nodes: status, pause, kill, resume")
    nodes = p.add_subparsers(dest="nodes_cmd", metavar="status|pause|kill|resume", required=True)
    q = nodes.add_parser("status", parents=common, help="the switch, its two files and the SUTRA_NODES_* settings")
    q.set_defaults(func=_status)
    for name, level, help_text in (("pause", "pause", "no new agent starts; the ones that run finish"), ("kill", "kill", "stop every agent now and start none")):
        q = nodes.add_parser(name, parents=common, help=help_text)
        q.add_argument("--reason", metavar="TEXT", default="", help="a few words for the audit")
        q.set_defaults(func=_write(level))
    q = nodes.add_parser("resume", parents=common, help="remove the pause and the kill switch")
    q.set_defaults(func=_resume)
    p.set_defaults(func=_status)
