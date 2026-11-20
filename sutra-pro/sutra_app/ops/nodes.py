"""`sutra-pro nodes status | pause | kill | resume`: the owner's switch for multi-agent nodes, by hand (guardrails 7; D279).

    sutra-pro nodes status [--json]            the switch (none, pause or kill), the two files, and the four SUTRA_NODES_* settings
    sutra-pro nodes pause [--reason TEXT]      put the PAUSE file in <data>/nodes: no new agent starts; the ones that run finish
    sutra-pro nodes kill [--reason TEXT]       put the KILL file there: a running Sutra stops every agent within a few seconds (its stop ladder) and none starts
    sutra-pro nodes resume                     remove both files

The command only writes and removes the two small files (it does not need the server, and it has no token to give one: a launch token is never written to disk). A running Sutra with
SUTRA_NODES_V1=1 looks for the KILL file every two seconds and runs the stop ladder; with it off nothing looks, and the command says so. A file left behind holds the agents back
if the feature is turned on later, which is the safe way round. Exit codes: 0 done, 2 a bad setting.
"""
import argparse
from typing import Any

from sutra_app.config import Settings
from sutra_app.ops.cli import common_parser, emit, load_settings
from sutra_app.orchestrator.killswitch import REASON_MAX, KillSwitch

__all__ = ["register"]


def _flags(settings: Settings) -> dict[str, bool]:
    return {"SUTRA_NODES_V1": settings.nodes_v1, "SUTRA_NODES_LANES": settings.nodes_lanes, "SUTRA_NODES_REVIEWER": settings.nodes_reviewer, "SUTRA_NODES_SLOTS": settings.nodes_slots}


def _off_note(settings: Settings) -> list[str]:
    return [] if settings.nodes_v1 else ["Note: SUTRA_NODES_V1 is 0 here, so a running Sutra does not look at these files and no agent runs. They hold agents back if you turn it on later."]


def _status(args: argparse.Namespace) -> int:
    settings = load_settings(args)
    if settings is None:
        return 2
    state = KillSwitch(settings.nodes_dir).status()
    payload: dict[str, Any] = {**state, "folder": str(settings.nodes_dir), "settings": _flags(settings)}
    words = {"none": "Agents may start.", "pause": "Paused: no new agent starts.", "kill": "Killed: every agent was stopped and none starts."}[state["level"]]
    lines = [f"nodes: {words}", f"  files in {settings.nodes_dir}: KILL {'present' if state['kill'] is not None else 'absent'}, PAUSE {'present' if state['pause'] is not None else 'absent'}"]
    for name in ("kill", "pause"):
        note = state[name]
        if note:
            lines.append(f"  {name.upper()}: " + "; ".join(f"{key} {note[key]}" for key in ("by", "reason", "at") if note.get(key)))
    lines.append("  settings: " + ", ".join(f"{name}={int(value)}" for name, value in _flags(settings).items()))
    lines += [f"  {line}" for line in _off_note(settings)]
    emit(args, payload, lines)
    return 0


def _write(level: str):
    def run(args: argparse.Namespace) -> int:
        settings = load_settings(args)
        if settings is None:
            return 2
        reason = " ".join((args.reason or "").split())[:REASON_MAX]
        KillSwitch(settings.nodes_dir).set(level, by="owner", reason=reason)
        done = ("Paused: no new agent starts; the ones that run finish." if level == "pause" else
                "Kill switch on: a running Sutra stops every agent within a few seconds, and none starts.")
        emit(args, {"level": level, "folder": str(settings.nodes_dir)}, [done, "Run `sutra-pro nodes resume` to remove it.", *_off_note(settings)])
        return 0
    return run


def _resume(args: argparse.Namespace) -> int:
    settings = load_settings(args)
    if settings is None:
        return 2
    removed = KillSwitch(settings.nodes_dir).clear()
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
