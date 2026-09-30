"""schedule.py — the launchd jobs that call run_sync.py on a schedule.

Separate from routines.py on purpose (see run_sync.py's docstring): routines.py's
launchd jobs run a Claude Code AGENT per fire; these run a plain Python script.
Same OS mechanism (launchd, because the app -- and its uvicorn child -- do not
exist while the window is closed, so an in-process timer would not fire), simpler
job: no prompt, no permission mode, no LLM billing, just
`<python> -m seo_agent.semrush.run_sync <mode>` on a fixed calendar interval.

Cadence (from the integration's design): daily for Position Tracking (matches
Semrush's own crawl cadence), weekly for the url_organic sweep (a normal-traffic
keyword's ranking does not move faster than that), monthly for backlinks (the
slowest-moving metric). All three land in the early morning, staggered ten minutes
apart so they never overlap on a slow morning.
"""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL_PREFIX = "os.sutra.ui.semrushsync."
MODES = ("daily", "weekly", "monthly")

# {mode: StartCalendarInterval}. Staggered starts, not simultaneous, so three jobs
# waking from sleep at once do not all hit the Semrush API in the same second.
_SCHEDULES = {
    "daily": {"Hour": 6, "Minute": 15},
    "weekly": {"Hour": 6, "Minute": 30, "Weekday": 1},     # Monday
    "monthly": {"Hour": 6, "Minute": 45, "Day": 1},
}


def _home():
    return Path(os.path.expanduser("~"))


def agents_dir():
    return Path(os.path.expanduser(
        os.environ.get("SUTRA_UI_LAUNCHAGENTS", "~/Library/LaunchAgents")))


def logs_dir():
    d = Path(os.path.expanduser("~/.sutra-ui/semrush-sync/logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def label_for(mode):
    return LABEL_PREFIX + mode


def plist_path(mode):
    return agents_dir() / (label_for(mode) + ".plist")


def _sutra_ui_dir():
    """The sutra-ui/ folder this file lives three levels under
    (seo_agent/semrush/schedule.py -> seo_agent/semrush -> seo_agent -> sutra-ui),
    so `python3 -m seo_agent.semrush.run_sync` resolves via cwd on sys.path exactly
    the way the app itself is run (app.py's own docstring: `python3 -m uvicorn app:app`,
    same directory)."""
    return str(Path(__file__).resolve().parents[2])


def build_plist(mode, python_bin=None, cwd=None):
    python_bin = python_bin or sys.executable
    cwd = cwd or _sutra_ui_dir()
    return {
        "Label": label_for(mode),
        "ProgramArguments": [python_bin, "-m", "seo_agent.semrush.run_sync", mode],
        "WorkingDirectory": cwd,
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(_home()),
        },
        "StandardOutPath": str(logs_dir() / (mode + ".log")),
        "StandardErrorPath": str(logs_dir() / (mode + ".log")),
        "StartCalendarInterval": dict(_SCHEDULES[mode]),
        "RunAtLoad": False,
        "ProcessType": "Background",
    }


def _run(cmd, timeout=60):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        class _R:
            returncode = -1
            stdout = ""
            stderr = str(exc)
        return _R()


def _uid():
    return os.getuid()


def write_plist(mode):
    agents_dir().mkdir(parents=True, exist_ok=True)
    p = plist_path(mode)
    data = plistlib.dumps(build_plist(mode))
    tmp = Path(str(p) + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o644)
    os.replace(str(tmp), str(p))
    lint = _run(["plutil", "-lint", str(p)])
    if lint.returncode != 0:
        raise RuntimeError("generated launchd job for %r is malformed: %s"
                           % (mode, (lint.stderr or lint.stdout or "").strip()))
    return p


def bootout(mode):
    return _run(["launchctl", "bootout", "gui/%d/%s" % (_uid(), label_for(mode))])


def bootstrap(mode):
    return _run(["launchctl", "bootstrap", "gui/%d" % _uid(), str(plist_path(mode))])


def install(mode):
    if mode not in MODES:
        raise ValueError("mode must be one of %s" % (MODES,))
    write_plist(mode)
    bootout(mode)          # ignore failure: may not have been loaded yet
    r = bootstrap(mode)
    return {"ok": r.returncode == 0, "mode": mode,
            "stderr": (r.stderr or "").strip() or None}


def install_all():
    return [install(m) for m in MODES]


def uninstall(mode):
    bootout(mode)
    p = plist_path(mode)
    if p.exists():
        p.unlink()
    return {"ok": True, "mode": mode}


def uninstall_all():
    return [uninstall(m) for m in MODES]


def job_state(mode):
    r = _run(["launchctl", "list", label_for(mode)])
    return {"loaded": r.returncode == 0}


def run_now(mode):
    """Fire it immediately, ignoring the schedule -- proves the job runs, not that
    the calendar interval will trigger it."""
    was_loaded = job_state(mode)["loaded"]
    if not was_loaded:
        write_plist(mode)
        bootstrap(mode)
    r = _run(["launchctl", "kickstart", "-k", "gui/%d/%s" % (_uid(), label_for(mode))])
    if not was_loaded:
        bootout(mode)
    return {"ok": r.returncode == 0, "mode": mode,
            "stderr": (r.stderr or "").strip() or None}


def status():
    return {"jobs": [{"mode": m, "label": label_for(m), **job_state(m),
                      "log": str(logs_dir() / (m + ".log"))} for m in MODES]}
