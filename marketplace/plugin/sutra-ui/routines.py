"""routines.py — scheduled routines that run on THIS machine.

Claude Code has two kinds. CLOUD routines live in the claude.ai account, run on
Anthropic's infrastructure, and have no local file format or scriptable CLI.
LOCAL scheduled tasks run on your machine. Only the second is something this
panel can honestly own end to end, so that is what this is. The UI says
"Routines" with a Local badge -- their noun, our scope, no implied parity.

WHY launchd AND NOT AN IN-APP TIMER
    electron/main.js quits the app when the last window closes and SIGKILLs the
    uvicorn child on the way out. The backend does not exist while the app is
    closed, so an in-process tick would fire approximately never -- not a
    scoped-down v1, a feature that does not work. launchd runs whether or not
    the app does.

    This does NOT contradict ADR-017. That decision is about the NATIVE engine's
    Trigger cadence, which must stay inside the daemon so every fire is an
    Execution with DecisionProvenance. A desktop routine is a different thing at
    a different layer: it has no TriggerEvent lifecycle to preserve.

WHAT A ROUTINE MAY DO, AND WHAT IT MAY NOT
    A routine runs an agent with nobody watching. The permission mode is a
    POSITIVE ALLOW-LIST here, not a subtraction from providers.PERMISSION_MODES:
    subtraction would silently re-admit bypassPermissions the day someone edits
    that tuple.

    The default is `dontAsk`, not `plan`. `plan` unattended is silent
    uselessness: it proposes edits for a human who is not there, exits 0, and
    the run reads OK while the routine does nothing forever. A routine that
    looks healthy and does nothing is worse than one that fails, because failure
    is legible. `dontAsk` denies rather than stalls.

    `dontAsk` IS WRITE-CAPABLE. This paragraph used to end "...and is not a
    write mode", and used to claim above that nothing "reaches a write-capable
    mode for a routine in v1". Both were false. `dontAsk` is a PROMPTING policy,
    not a capability: providers.py's own PERMISSION_MODE_NOTES already says it
    "never prompts. Actions the rules do not already allow are declined rather
    than escalated." What a run may actually do is decided by the loaded rules
    -- and this module already emits `opts.allowed_tools` verbatim as repeated
    --allowed-tools flags in the runner's argv. Measured against the CLI
    directly, 2026-08-18:

        --permission-mode dontAsk --allowed-tools Write   -> the file CHANGED
        --permission-mode dontAsk (no allow-list)         -> Write DENIED
        --permission-mode plan    --allowed-tools Write   -> not written

    So the real ceiling on a routine is the pair (permission_mode,
    allowed_tools), and validate_new only validates the first half. Anything
    relying on "a routine cannot write" is relying on a property this module
    does not have.

    One more thing the pair does not capture: `--setting-sources user` is
    hardcoded in the runner, so a routine also inherits the operator's own
    PreToolUse hooks. Those can deny a tool for reasons unrelated to permission
    mode, and the run presents as a spent budget and a non-zero exit rather than
    as a legible refusal.
"""
import errno
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
LABEL_PREFIX = "os.sutra.ui.routine."
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

#: POSITIVE allow-list. See the module docstring -- do not derive this by
#: subtracting from providers.PERMISSION_MODES.
ROUTINE_PERMISSION_MODES = ("dontAsk", "plan")
DEFAULT_ROUTINE_MODE = "dontAsk"

MODELS = ("", "opus", "sonnet", "haiku")
PRESETS = ("manual", "hourly", "daily", "weekdays", "weekly", "custom")

RUN_INDEX = "index.jsonl"
MAX_OUTPUT_BYTES = 256 * 1024          # per run; the tail is what diagnoses a failure
RUN_TIMEOUT_S = 30 * 60                # watchdog: an unattended turn may not run forever


def _home():
    return Path(os.path.expanduser("~"))


def store_dir():
    return Path(os.path.expanduser(
        os.environ.get("SUTRA_UI_ROUTINES", "~/.sutra-ui/routines")))


def runs_dir():
    return Path(os.path.expanduser(
        os.environ.get("SUTRA_UI_RUNS", "~/.sutra-ui/runs")))


def agents_dir():
    return Path(os.path.expanduser(
        os.environ.get("SUTRA_UI_LAUNCHAGENTS", "~/Library/LaunchAgents")))


def _mkdir_private(p):
    """0700, explicitly. mkdir(mode=) is masked by umask, and this store holds
    prompts and captured agent output."""
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass
    return p


def _write_private(path, text):
    """Create 0600 or fail. O_EXCL then replace, so a reader never sees a
    half-written record and the mode is never wider than intended."""
    tmp = Path(str(path) + ".tmp")
    if tmp.exists():
        tmp.unlink()
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(str(tmp), str(path))


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def label_for(rid):
    return LABEL_PREFIX + rid


def plist_path(rid):
    return agents_dir() / (label_for(rid) + ".plist")


# ------------------------------------------------------------- schedule -----
# Cron is canonical because it is the vocabulary the operator already has;
# StartCalendarInterval is DERIVED from it by a pure function so the two can
# never drift apart in the record.

_DAY_NAMES = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday",
              "Friday", "Saturday")


def _expand_field(spec, lo, hi):
    """One cron field -> sorted ints. Grammar: * , a-b , */n , lists.

    Deliberately NOT supported: L, W, ?, MON-style aliases. Refused by name
    rather than silently misinterpreted -- a schedule that means something other
    than what was typed is worse than one that is rejected.
    """
    out = set()
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            raise ValueError("empty field in cron expression")
        step = 1
        if "/" in part:
            part, _, s = part.partition("/")
            if not s.isdigit() or int(s) < 1:
                raise ValueError("step must be a positive integer, got %r" % s)
            step = int(s)
        if part == "*":
            lo_, hi_ = lo, hi
        elif "-" in part.lstrip("-"):
            a, _, b = part.partition("-")
            if not (a.isdigit() and b.isdigit()):
                raise ValueError("range must be numeric, got %r" % part)
            lo_, hi_ = int(a), int(b)
        elif part.isdigit():
            lo_ = hi_ = int(part)
        else:
            raise ValueError(
                "unsupported cron token %r -- this accepts *, numbers, a-b, "
                "lists and */n only (no L, W, ? or day names)" % part)
        if lo_ < lo or hi_ > hi or lo_ > hi_:
            raise ValueError("value out of range in %r (allowed %d-%d)" % (part, lo, hi))
        out.update(range(lo_, hi_ + 1, step))
    return sorted(out)


def parse_cron(cron):
    """5-field cron -> {minute, hour, dom, month, dow} of int lists."""
    parts = str(cron or "").split()
    if len(parts) != 5:
        raise ValueError("a cron expression has 5 fields (minute hour day month weekday), got %d"
                         % len(parts))
    m, h, dom, mon, dow = parts
    return {
        "minute": _expand_field(m, 0, 59),
        "hour": _expand_field(h, 0, 23),
        "dom": _expand_field(dom, 1, 31),
        "month": _expand_field(mon, 1, 12),
        # 0 and 7 are BOTH Sunday in cron; launchd wants 0-6.
        "dow": sorted({0 if d == 7 else d for d in _expand_field(dow, 0, 7)}),
    }


def validate_cron(cron):
    """Reject at CREATE time what would otherwise be discovered at 09:00.

    The single-minute rule IS the hourly floor: an unattended agent every 15
    minutes is a cost incident, not a feature. `0 9,17 * * *` passes (twice a
    day); `*/15 * * * *` does not.
    """
    f = parse_cron(cron)
    if len(f["minute"]) != 1:
        raise ValueError(
            "a routine may fire at most once per hour, so the minute field must "
            "be a single value (got %d). '0 9,17 * * *' is fine; '*/15 * * * *' "
            "is not." % len(f["minute"]))
    return f


def cron_to_calendar(cron):
    """cron -> StartCalendarInterval dict | list[dict]. Pure.

    Omitted keys are crontab-style WILDCARDS to launchd, so only constrained
    fields are emitted. A cartesian product is used where more than one field is
    constrained, because launchd has no range syntax of its own.
    """
    f = validate_cron(cron)
    full = {"minute": 60, "hour": 24, "dom": 31, "month": 12, "dow": 7}
    keys = {"minute": "Minute", "hour": "Hour", "dom": "Day",
            "month": "Month", "dow": "Weekday"}
    constrained = [k for k in ("minute", "hour", "dom", "month", "dow")
                   if len(f[k]) < full[k]]
    combos = [{}]
    for k in constrained:
        combos = [dict(c, **{keys[k]: v}) for c in combos for v in f[k]]
    combos = [c for c in combos if c]
    if not combos:
        return {"Minute": 0}          # "* * * * *" would be every minute; floor it
    return combos[0] if len(combos) == 1 else combos


def preset_to_cron(preset, hour=9, minute=0, weekday=1, cron=None):
    """The five presets Claude's own Schedule control offers, plus custom."""
    preset = (preset or "manual").lower()
    if preset not in PRESETS:
        raise ValueError("unknown schedule preset %r -- one of: %s"
                         % (preset, ", ".join(PRESETS)))
    if preset == "manual":
        return None
    if preset == "custom":
        if not cron:
            raise ValueError("a custom schedule needs a cron expression")
        validate_cron(cron)
        return cron.strip()
    hour, minute = int(hour), int(minute)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time must be 00:00-23:59")
    if preset == "hourly":
        return "%d * * * *" % minute
    if preset == "daily":
        return "%d %d * * *" % (minute, hour)
    if preset == "weekdays":
        return "%d %d * * 1-5" % (minute, hour)
    if preset == "weekly":
        weekday = int(weekday)
        if not (0 <= weekday <= 6):
            raise ValueError("weekday must be 0 (Sunday) to 6 (Saturday)")
        return "%d %d * * %d" % (minute, hour, weekday)
    raise ValueError("unreachable preset %r" % preset)


def human_schedule(preset, cron):
    """Self-describing text, stored on the record so it reads correctly outside
    the app. Always says LOCAL: launchd fires in local time and the difference
    matters twice a year."""
    if not cron:
        return "Manual — only when you run it"
    try:
        f = parse_cron(cron)
    except ValueError:
        return cron
    hh = f["hour"][0] if len(f["hour"]) == 1 else None
    mm = f["minute"][0]
    t = ("%d:%02d" % (((hh - 1) % 12) + 1, mm)) + (" AM" if hh is not None and hh < 12 else " PM") \
        if hh is not None else None
    if preset == "hourly":
        return "Every hour at :%02d (local)" % mm
    if preset == "daily" and t:
        return "Every day at %s (local)" % t
    if preset == "weekdays" and t:
        return "Weekdays at %s (local)" % t
    if preset == "weekly" and t and len(f["dow"]) == 1:
        return "Every %s at %s (local)" % (_DAY_NAMES[f["dow"][0]], t)
    return "%s (local)" % cron


# --------------------------------------------------------------- runner -----
# COPIED OUT OF THE BUNDLE, on purpose. The .app is replaced wholesale by the
# updater and can be deleted entirely; a launchd job pointing into it would
# start failing, or worse, keep pointing at a stale copy. It also self-uninstalls
# when the store is gone -- macOS has no uninstall hook, and nothing else would
# ever clean these jobs up.

RUNNER_NAME = "run-routine.py"
_RUNNER = r'''#!/usr/bin/env python3
"""Sutra routine runner. Copied out of the app bundle; do not edit here.

Runs ONE routine and appends ONE run record. Self-contained by design: it must
keep working when the .app is mid-update or gone.
"""
import json, os, re, subprocess, sys, time, hashlib, shutil
from datetime import datetime, timezone

STORE = os.path.expanduser(os.environ.get("SUTRA_UI_ROUTINES", "~/.sutra-ui/routines"))
RUNS  = os.path.expanduser(os.environ.get("SUTRA_UI_RUNS", "~/.sutra-ui/runs"))
MAX_OUT = 256 * 1024
TIMEOUT = 30 * 60

def iso(): return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def selfdestruct(rid, why):
    """The store is gone -> this job must remove itself. Nothing else will."""
    label = "os.sutra.ui.routine." + rid
    sys.stderr.write("sutra-routine: %s; removing %s\n" % (why, label))
    try:
        subprocess.run(["launchctl", "bootout", "gui/%d/%s" % (os.getuid(), label)],
                       capture_output=True, timeout=30)
    except Exception:
        pass
    p = os.path.expanduser("~/Library/LaunchAgents/%s.plist" % label)
    try:
        os.unlink(p)
    except OSError:
        pass
    sys.exit(0)

def login_path():
    """launchd hands a job PATH=/usr/bin:/bin:/usr/sbin:/sbin, on which a
    Homebrew or nvm `claude` is invisible -- and a missing binary shows up as a
    HANG, not an error. Re-harvest at fire time: interactive first, because zsh
    reads ~/.zshrc only for interactive shells and that is where nvm,
    npm-global and Claude's own installer put PATH."""
    sh = os.environ.get("SHELL") or "/bin/zsh"
    if not os.path.isfile(sh): sh = "/bin/zsh"
    seen, out = set(), []
    for flags in (["-l","-i","-c"], ["-l","-c"]):
        try:
            r = subprocess.run([sh] + flags + ['command -p echo "$PATH"'],
                               capture_output=True, text=True, timeout=15)
        except Exception:
            continue
        lines = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
        if not lines: continue
        cand = lines[-1]
        if ":" not in cand or not cand.startswith("/"): continue
        for e in cand.split(":"):
            if e and e not in seen:
                seen.add(e); out.append(e)
    for e in (os.environ.get("PATH") or "").split(":"):
        if e and e not in seen:
            seen.add(e); out.append(e)
    return ":".join(out)


# ---- teamsutra queue (active only when the record opts in) -----------------
# The runner stays stdlib-only and generic; everything task-specific keys off
# opts.teamsutra == true on the routine record. One task per fire, oldest
# first by created_ms (never directory order). A crashed claim stays claimed
# on purpose -- release is an operator CLICK, never a timer, so a crash can
# never become a retry loop.
TS_DIR = os.path.expanduser(os.environ.get("SUTRA_UI_TEAMSUTRA", "~/.sutra-ui/teamsutra"))

def ts_write(path, rec):
    tmp = path + ".sutra-tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(rec, indent=2).encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, path)

def ts_claim():
    """Oldest queued task, or None. Corrupt files are skipped -- the panel
    surfaces them; one bad record must never halt the sweep."""
    try:
        names = [n for n in os.listdir(TS_DIR)
                 if n.startswith("t-") and n.endswith(".json")]
    except OSError:
        return None, None
    best = None
    for n in names:
        fp = os.path.join(TS_DIR, n)
        try:
            with open(fp, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        if rec.get("schema") != 1 or rec.get("status") != "queued":
            continue
        key = (rec.get("created_ms") or 0, rec.get("id") or "")
        if best is None or key < best[0]:
            best = (key, fp, rec)
    if best is None:
        return None, None
    _, fp, rec = best
    rec["status"] = "claimed"
    rec["attempts"] = int(rec.get("attempts") or 0) + 1
    rec["updated_at"] = iso()
    ts_write(fp, rec)
    return fp, rec

def ts_extract_diff(text):
    """The worker is READ-ONLY: its fix arrives as a unified diff in its final
    message. Last ```diff fence wins; else a bare ---/+++ hunk block."""
    text = text or ""
    fences = re.findall(r"```diff\n(.*?)```", text, re.S)
    if fences:
        return fences[-1].strip() or None
    i = text.find("--- a/")
    if i != -1 and "+++ b/" in text[i:]:
        return text[i:].strip() or None
    return None

def ts_scrub_env(env):
    """The verify subprocess gets NO credential-shaped env. Pattern-based on
    purpose: a fixed list is stale the day a new token variable appears."""
    bad = re.compile(r"(TOKEN|SECRET|PASSWORD|API_?KEY|CREDENTIAL|_PAT$|^GH_|^GITHUB_|^AWS_|^OPENAI_|^ANTHROPIC_|^COMPOSIO_)", re.I)
    return {k: v for k, v in env.items() if not bad.search(k)}

def ts_finish(fp, rec, status, **fields):
    rec["status"] = status
    for k, v in fields.items():
        rec[k] = v
    rec["updated_at"] = iso()
    ts_write(fp, rec)

def main():
    if len(sys.argv) < 2: sys.exit(2)
    rid = sys.argv[1]
    # TRIGGER, and it must be honest. `launchctl kickstart` reuses the plist's
    # own ProgramArguments, so argv cannot distinguish "the schedule fired" from
    # "a human pressed Run now" -- every run would claim to be scheduled, and the
    # UI could never tell you your schedule has never actually fired. run_now()
    # drops a marker just before kickstarting; this consumes it.
    trigger = "schedule"
    marker = os.path.join(RUNS, rid, ".manual")
    try:
        os.unlink(marker); trigger = "manual"
    except OSError:
        pass
    rec_path = os.path.join(STORE, rid + ".json")
    if not os.path.isdir(STORE): selfdestruct(rid, "routine store is gone")
    if not os.path.isfile(rec_path): selfdestruct(rid, "routine record is gone")
    with open(rec_path, encoding="utf-8") as fh:
        r = json.load(fh)

    rundir = os.path.join(RUNS, rid)
    os.makedirs(rundir, exist_ok=True)
    try: os.chmod(rundir, 0o700)
    except OSError: pass

    # OVERLAP LOCK. mkdir is atomic. A slow routine must not stack copies of
    # itself; the second fire records that it was skipped rather than vanishing.
    lock = os.path.join(rundir, ".lock")
    started = iso(); t0 = time.time()
    try:
        os.mkdir(lock)
    except OSError:
        row = {"schema":1,"id":rid,"trigger":trigger,"started_at":started,
               "outcome":"skipped","reason":"a previous run is still going",
               "duration_s":0}
        append(rundir, row); return

    # OUTER GUARD (codex P1): everything after the lock is acquired runs under
    # one try/finally. Before this, argv construction sat OUTSIDE the try that
    # releases .lock -- one bad task payload or a NameError in new code would
    # strand the lock (and any claim) forever with no index row.
    ts_fp = ts_rec = None
    try:
        env = dict(os.environ)
        env["PATH"] = login_path()
        # NEVER inherited into a routine: it would route billing through the
        # per-token API instead of the plan, silently, on a schedule.
        env.pop("ANTHROPIC_API_KEY", None)

        prompt = r["prompt"]
        if (r.get("opts") or {}).get("teamsutra"):
            ts_fp, ts_rec = ts_claim()
            if ts_rec is None:
                append(rundir, {"schema":1,"id":rid,"trigger":trigger,
                                "started_at":started,"outcome":"skipped",
                                "reason":"teamsutra queue empty","duration_s":0})
                return
            src = ts_rec.get("source") or {}
            prompt = (prompt + "\n\n== TASK " + ts_rec["id"] + " (attempt "
                      + str(ts_rec.get("attempts")) + " of "
                      + str(ts_rec.get("max_attempts")) + ") ==\nTITLE: "
                      + (ts_rec.get("title") or "") + "\nKIND: "
                      + (ts_rec.get("kind") or "") + "\nDEPARTMENT: "
                      + (src.get("domain_path") or "none") + " "
                      + (src.get("domain_name") or "") + "\nSELECTION:\n"
                      + (src.get("selection") or "(none)") + "\n\nBODY:\n"
                      + (ts_rec.get("body") or ""))

        claude = shutil.which("claude", path=env["PATH"]) or r.get("claude_bin") or "claude"
        args = [claude, "-p", prompt, "--output-format", "json",
                "--permission-mode", r.get("permission_mode") or "dontAsk",
                "--setting-sources", (r.get("opts") or {}).get("setting_sources") or "user"]
        if r.get("model"): args += ["--model", r["model"]]
        o = r.get("opts") or {}
        if o.get("effort"): args += ["--effort", str(o["effort"])]
        if o.get("max_budget_usd"): args += ["--max-budget-usd", str(o["max_budget_usd"])]
        for t in (o.get("allowed_tools") or []): args += ["--allowed-tools", t]
        for t in (o.get("disallowed_tools") or []): args += ["--disallowed-tools", t]

        outp = os.path.join(rundir, started.replace(":", "-") + ".out")
        outcome, exit_code, detail, cost = "ok", None, None, None
        result_text = ""
        try:
            p = subprocess.run(args, cwd=r.get("cwd") or os.path.expanduser("~"),
                               env=env, capture_output=True, text=True, timeout=TIMEOUT)
            exit_code = p.returncode
            body = (p.stdout or "") + (("\n--- stderr ---\n" + p.stderr) if p.stderr else "")
            fd = os.open(outp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try: os.write(fd, body[-MAX_OUT:].encode("utf-8", "replace"))
            finally: os.close(fd)
            if exit_code != 0:
                outcome = "failed"; detail = (p.stderr or p.stdout or "")[-600:]
            else:
                try:
                    j = json.loads(p.stdout or "{}")
                    cost = j.get("total_cost_usd")
                    result_text = str(j.get("result") or "")
                    if j.get("is_error"): outcome, detail = "failed", str(j.get("subtype") or "")[:200]
                except ValueError:
                    pass
        except subprocess.TimeoutExpired:
            outcome, detail = "timeout", "exceeded %ds" % TIMEOUT
        except OSError as e:
            outcome, detail = "failed", "could not start claude: %s" % e

        verify_exit = None
        if ts_rec is not None:
            # The worker is READ-ONLY; its output is a unified diff (or an
            # explicit refusal). Close the task honestly from what came back.
            if outcome == "ok":
                diff = ts_extract_diff(result_text)
                m = re.search(r"^BLOCKED:\s*(.+)$", result_text, re.M)
                if diff:
                    if (ts_rec.get("verify") or "").strip():
                        try:
                            v = subprocess.run(["/bin/sh", "-c", ts_rec["verify"]],
                                               cwd=r.get("cwd") or os.path.expanduser("~"),
                                               env=ts_scrub_env(env), capture_output=True,
                                               text=True, timeout=120)
                            verify_exit = v.returncode
                        except Exception:
                            verify_exit = -1
                    ts_finish(ts_fp, ts_rec, "needs_review", diff=diff,
                              last_error=None)
                elif m:
                    ts_finish(ts_fp, ts_rec, "blocked",
                              blocked_reason=m.group(1)[:600])
                else:
                    ts_finish(ts_fp, ts_rec, "failed",
                              last_error="worker returned neither a diff nor a BLOCKED: line")
            else:
                ts_finish(ts_fp, ts_rec, "failed",
                          last_error=(detail or outcome or "")[:600])

        append(rundir, {"schema":1,"id":rid,"trigger":trigger,"started_at":started,
                        "ended_at":iso(),"duration_s":round(time.time()-t0,1),
                        "outcome":outcome,"exit_code":exit_code,"detail":detail,
                        "cost_usd":cost,"output_file":os.path.basename(outp),
                        "task_id":(ts_rec or {}).get("id"),
                        "verify_exit":verify_exit,
                        "prompt_sha256":hashlib.sha256((r.get("prompt") or "").encode()).hexdigest()})
    except Exception as e:
        # The outer guard's whole point: an unexpected raise still writes a
        # legible failure row and closes the task, instead of stranding both.
        try:
            if ts_rec is not None and ts_rec.get("status") == "claimed":
                ts_finish(ts_fp, ts_rec, "failed",
                          last_error=("runner error: %s" % e)[:600])
        except Exception:
            pass
        append(rundir, {"schema":1,"id":rid,"trigger":trigger,"started_at":started,
                        "ended_at":iso(),"duration_s":round(time.time()-t0,1),
                        "outcome":"failed","exit_code":None,
                        "detail":("runner error: %s" % e)[:600],
                        "task_id":(ts_rec or {}).get("id")})
    finally:
        try: os.rmdir(lock)
        except OSError: pass

def append(rundir, row):
    p = os.path.join(rundir, "index.jsonl")
    exists = os.path.exists(p)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    if not exists:
        try: os.chmod(p, 0o600)
        except OSError: pass

main()
'''


def runner_path():
    return store_dir() / "bin" / RUNNER_NAME


def runner_syntax_error(source=None):
    """Return a human-readable reason _RUNNER will not parse, or None.

    WHY THIS EXISTS. The runner is a STRING literal in this module, not an
    imported module: nothing type-checks it, no linter walks it, and no test
    imports it. A typo therefore ships silently and does not surface until
    launchd fires the job -- possibly hours later, on a machine nobody is
    watching, as a bare non-zero exit with a traceback buried in a .out file.

    compile() rather than py_compile: py_compile wants a path on disk, and the
    whole point is to find out BEFORE anything reaches disk.
    """
    try:
        compile(_RUNNER if source is None else source, RUNNER_NAME, "exec")
    except SyntaxError as e:
        return "line %s: %s" % (e.lineno, e.msg)
    return None


def install_runner():
    """Write the runner out of the bundle. Idempotent; rewritten when it drifts,
    so an app update carries a new runner to already-scheduled routines.

    Refuses to install a runner that does not parse. The check runs BEFORE the
    write on purpose: a broken runner must never replace a working one that is
    already on disk serving scheduled jobs. Failing here is loud and happens
    while a human is present; failing at fire time is silent and is not.
    """
    want = _RUNNER
    bad = runner_syntax_error(want)
    if bad:
        raise ValueError(
            "refusing to install %s: it does not parse (%s). The runner is a "
            "string literal in routines.py, so this is an edit to _RUNNER, not "
            "a corrupt file on disk." % (RUNNER_NAME, bad))
    d = _mkdir_private(store_dir() / "bin")
    p = d / RUNNER_NAME
    if not p.exists() or p.read_text(encoding="utf-8") != want:
        _write_private(p, want)
    os.chmod(p, 0o700)
    return p


def runner_sha():
    return hashlib.sha256(_RUNNER.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------- launchd ----

def _uid():
    return os.getuid()


def _run(cmd, timeout=60):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        class _R:
            returncode = -1
            stdout = ""
            stderr = str(exc)
        return _R()


def build_plist(rec):
    """The launchd job for one routine. plistlib, so quoting is never our problem."""
    rid = rec["id"]
    d = {
        "Label": label_for(rid),
        "ProgramArguments": ["/usr/bin/python3", str(runner_path()), rid, "schedule"],
        "WorkingDirectory": rec.get("cwd") or str(_home()),
        "EnvironmentVariables": {
            # STRINGS ONLY -- launchd silently ignores non-string values. This is
            # the FALLBACK path; the runner re-harvests the real one at fire time.
            "PATH": "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:"
                    "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": str(_home()),
            "SUTRA_UI_ROUTINE": rid,
        },
        "StandardOutPath": str(runs_dir() / rid / "launchd.log"),
        "StandardErrorPath": str(runs_dir() / rid / "launchd.log"),
        # A routine must NOT fire merely because you logged in.
        "RunAtLoad": False,
        # LOAD-BEARING: `claude` credentials live in the login keychain, which a
        # non-Aqua background job can meet locked, with no token and no way to say so.
        "LimitLoadToSessionType": "Aqua",
        "AssociatedBundleIdentifiers": ["os.sutra.ui"],
        # An LLM turn is not background housekeeping; unset ProcessType throttles CPU/IO.
        "ProcessType": "Standard",
        "ExitTimeOut": 30,
    }
    cron = (rec.get("schedule") or {}).get("cron")
    if cron:
        d["StartCalendarInterval"] = cron_to_calendar(cron)
    return d


def write_plist(rec):
    """Write + `plutil -lint`. Linting every write matters because a malformed
    plist otherwise fails opaquely later, at bootstrap, far from the cause."""
    agents_dir().mkdir(parents=True, exist_ok=True)
    p = plist_path(rec["id"])
    data = plistlib.dumps(build_plist(rec))
    tmp = Path(str(p) + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o644)          # launchd refuses group/world-writable plists
    os.replace(str(tmp), str(p))
    lint = _run(["plutil", "-lint", str(p)])
    if lint.returncode != 0:
        raise RuntimeError("the generated launchd job is malformed: %s"
                           % (lint.stderr or lint.stdout or "").strip())
    return p


def bootout(rid):
    """Service-target form, NOT the plist form -- it still works after the plist
    is gone, which is exactly when it is needed."""
    return _run(["launchctl", "bootout", "gui/%d/%s" % (_uid(), label_for(rid))])


def bootstrap(rid):
    return _run(["launchctl", "bootstrap", "gui/%d" % _uid(), str(plist_path(rid))])


def kickstart(rid):
    """Runs regardless of configured launch conditions -- so it proves the
    runner, NOT the schedule. The UI has to say so."""
    return _run(["launchctl", "kickstart", "-k",
                 "gui/%d/%s" % (_uid(), label_for(rid))])


def job_state(rid):
    """{loaded, last_exit_status}. rc 113 from `launchctl list` = not loaded.

    `launchctl print` is never parsed: its own man page says the output "is NOT
    API in any sense at all".
    """
    r = _run(["launchctl", "list", label_for(rid)])
    if r.returncode != 0:
        return {"loaded": False, "last_exit_status": None,
                "detail": (r.stderr or "").strip() or None}
    m = re.search(r'"LastExitStatus"\s*=\s*(-?\d+)', r.stdout or "")
    return {"loaded": True,
            "last_exit_status": int(m.group(1)) if m else None,
            "detail": None}


def reload_job(rec):
    """launchd does not re-read a plist in place; there is no 'reload'."""
    bootout(rec["id"])                     # may legitimately fail: not loaded yet
    write_plist(rec)
    r = bootstrap(rec["id"])
    return {"ok": r.returncode == 0,
            "stderr": (r.stderr or r.stdout or "").strip() or None}


# ----------------------------------------------------------------- store ----

def _rec_path(rid):
    return store_dir() / (rid + ".json")


def validate_new(body, existing_ids):
    """Everything that can be refused is refused HERE, while the operator is
    still present to be told -- not at 09:00 with nobody watching."""
    rid = str(body.get("id") or "").strip().lower()
    if not ID_RE.match(rid):
        raise ValueError("id must be kebab-case, 1-48 chars, starting with a "
                         "letter or digit (got %r)" % rid)
    if rid in existing_ids:
        raise ValueError("a routine called %r already exists" % rid)

    desc = str(body.get("description") or "").strip()
    if not 1 <= len(desc) <= 200:
        raise ValueError("description is required, 1-200 characters -- it is the "
                         "only thing that makes a list of routines scannable")

    prompt = str(body.get("prompt") or "").strip()
    if not 1 <= len(prompt) <= 100000:
        raise ValueError("prompt is required")

    cwd = os.path.realpath(os.path.expanduser(str(body.get("cwd") or "")))
    if not cwd or not os.path.isdir(cwd):
        raise ValueError("working folder %r does not exist -- a routine must "
                         "name a real directory before it can be saved" % cwd)
    home = os.path.realpath(str(_home()))
    if not (cwd == home or cwd.startswith(home + os.sep)):
        raise ValueError("working folder must be inside your home directory")

    mode = body.get("permission_mode") or DEFAULT_ROUTINE_MODE
    if mode not in ROUTINE_PERMISSION_MODES:
        raise ValueError(
            "a routine runs unattended, so it may only use %s. %r auto-approves "
            "agent actions and is not available to a routine at all."
            % (" or ".join(ROUTINE_PERMISSION_MODES), mode))

    model = body.get("model") or ""
    if model not in MODELS:
        raise ValueError("unknown model %r" % model)

    sched = body.get("schedule") or {}
    cron = preset_to_cron(sched.get("preset") or "manual",
                          hour=sched.get("hour", 9), minute=sched.get("minute", 0),
                          weekday=sched.get("weekday", 1), cron=sched.get("cron"))

    opts = dict(body.get("opts") or {})
    budget = opts.get("max_budget_usd", 1.0)
    try:
        budget = float(budget)
    except (TypeError, ValueError):
        raise ValueError("max_budget_usd must be a number")
    if budget <= 0:
        raise ValueError("max_budget_usd must be greater than 0 -- an unattended "
                         "run with no ceiling is how a schedule becomes a bill")
    opts["max_budget_usd"] = budget
    opts.setdefault("setting_sources", "user")
    if opts["setting_sources"] not in ("user", "user,project"):
        raise ValueError("setting_sources must be 'user' or 'user,project'")

    return {
        "schema": SCHEMA,
        "id": rid,
        "description": desc,
        "prompt": prompt,
        "cwd": cwd,
        "model": model,
        "permission_mode": mode,
        "opts": opts,
        "schedule": {"preset": sched.get("preset") or "manual", "cron": cron,
                     "human": human_schedule(sched.get("preset") or "manual", cron)},
        "enabled": bool(body.get("enabled", True)),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "claude_bin": shutil.which("claude") or "",
        "auto_disabled": None,
    }


def list_ids():
    d = store_dir()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def load(rid):
    p = _rec_path(rid)
    if not p.is_file():
        raise KeyError(rid)
    rec = json.loads(p.read_text(encoding="utf-8"))
    if rec.get("schema") != SCHEMA:
        raise ValueError("routine %r was written by a different version of Sutra "
                         "(schema %r). Refusing to half-interpret it."
                         % (rid, rec.get("schema")))
    return rec


def save(rec):
    _mkdir_private(store_dir())
    rec["updated_at"] = now_iso()
    _write_private(_rec_path(rec["id"]), json.dumps(rec, indent=2) + "\n")
    return rec


def create(body):
    rec = validate_new(body, set(list_ids()))
    install_runner()
    _mkdir_private(runs_dir() / rec["id"])
    save(rec)
    launchd = reload_job(rec) if rec["enabled"] else {"ok": True, "stderr": None,
                                                      "note": "paused; not loaded"}
    if rec["enabled"] and not launchd["ok"]:
        # Kept, not discarded: the record is valid and the operator can retry.
        # Silently deleting it would hide the only copy of their prompt.
        launchd["note"] = ("saved, but launchd refused to load it -- it will not "
                           "fire until this is fixed")
    return rec, launchd


def update(rid, body):
    rec = load(rid)
    resched = False
    for k in ("description", "prompt", "cwd", "model", "permission_mode",
              "spend_window_usd"):
        if k in body and body[k] is not None:
            rec[k] = body[k]
    if "opts" in body and body["opts"] is not None:
        rec["opts"] = dict(rec.get("opts") or {}, **body["opts"])
    if "schedule" in body and body["schedule"]:
        s = body["schedule"]
        cron = preset_to_cron(s.get("preset") or "manual", hour=s.get("hour", 9),
                              minute=s.get("minute", 0), weekday=s.get("weekday", 1),
                              cron=s.get("cron"))
        rec["schedule"] = {"preset": s.get("preset") or "manual", "cron": cron,
                           "human": human_schedule(s.get("preset") or "manual", cron)}
        resched = True
    if "enabled" in body:
        rec["enabled"] = bool(body["enabled"])
        resched = True
    if body.get("clear_auto_disable"):
        rec["auto_disabled"] = None
    # Re-validate the whole record, so an update cannot reach a state create refuses.
    checked = validate_new(dict(rec, id=rec["id"]), set())
    for k in ("description", "prompt", "cwd", "model", "permission_mode", "opts"):
        rec[k] = checked[k]
    rec["prompt_sha256"] = checked["prompt_sha256"]
    save(rec)
    if resched:
        launchd = reload_job(rec) if rec["enabled"] else _paused(rid)
    else:
        launchd = {"ok": True, "stderr": None}
    return rec, launchd


def _paused(rid):
    r = bootout(rid)
    return {"ok": True, "stderr": None,
            "note": "paused — the job is unloaded, so it cannot fire. "
                    "Run now still works.",
            "bootout": (r.stderr or "").strip() or None}


def delete(rid):
    """bootout BEFORE unlink, never the reverse: a loaded job whose plist is gone
    is the one state the UI cannot clean up from."""
    load(rid)
    r = bootout(rid)
    err = (r.stderr or "").strip()
    # "No such process" is success for our purposes: it is already not loaded.
    if r.returncode != 0 and "no such process" not in err.lower() \
            and "could not find" not in err.lower():
        raise RuntimeError("could not unload the scheduled job, so it was NOT "
                           "deleted: %s" % err)
    p = plist_path(rid)
    if p.exists():
        p.unlink()
    _rec_path(rid).unlink()
    return {"deleted": True, "kept_runs": True,
            "note": "run history kept at %s" % (runs_dir() / rid)}


# ------------------------------------------------------------------ runs ----

def runs(rid, limit=10):
    d = runs_dir() / rid
    idx = d / RUN_INDEX
    if not idx.is_file():
        return {"id": rid, "total": 0, "runs": [], "unreadable": 0,
                "never_run": True}
    rows, bad = [], 0
    for line in idx.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            bad += 1
    return {"id": rid, "total": len(rows), "runs": rows[-limit:][::-1],
            "unreadable": bad, "never_run": not rows}


def run_output(rid, name):
    """One run's captured output. The filename comes from the index, never from
    the client -- a basename check is what keeps it that way."""
    if os.path.basename(name) != name:
        raise ValueError("bad output name")
    p = runs_dir() / rid / name
    if not p.is_file():
        raise KeyError(name)
    return p.read_text(encoding="utf-8", errors="replace")


def run_detail(rid, name):
    """One run, parsed into something readable and resumable.

    Every run is already stored as the raw JSON `claude -p --output-format json`
    wrote, and that blob has always carried two things nothing ever read:

      result      -- the assistant's actual prose, which is what a person wants
                     to see. The raw envelope around it (ttft_ms, modelUsage,
                     permission_denials...) is telemetry, not the answer.
      session_id  -- the thread the run happened on. Because it was written at
                     the time, EVERY HISTORICAL RUN IS ALREADY RESUMABLE; this
                     needs no new capture and works retroactively on runs
                     recorded months ago.

    Falls back to the raw text when the blob is not the expected shape -- a run
    that failed before claude emitted JSON still has stderr worth reading, and
    showing nothing because it did not parse would hide the failure.
    """
    raw = run_output(rid, name)
    out = {"id": rid, "name": name, "text": raw, "parsed": False,
           "result": None, "session_id": None, "turns": None,
           "cost_usd": None, "is_error": None, "stop_reason": None}
    try:
        j = json.loads(raw)
    except ValueError:
        return out
    if not isinstance(j, dict):
        return out
    out.update({
        "parsed": True,
        "result": j.get("result"),
        "session_id": j.get("session_id"),
        "turns": j.get("num_turns"),
        "cost_usd": j.get("total_cost_usd"),
        "is_error": bool(j.get("is_error")),
        "stop_reason": j.get("stop_reason") or j.get("subtype"),
        # Surfaced because it EXPLAINS an empty result: a run that was denied a
        # tool produced no answer for a reason, and "nothing here" without the
        # reason reads as the routine being broken.
        "permission_denials": j.get("permission_denials") or [],
    })
    return out


def run_now(rid):
    rec = load(rid)
    install_runner()
    # A paused routine is unloaded, so kickstart has nothing to target. Load it,
    # fire, and unload again -- "Run now still works while paused" is the
    # behaviour Claude has, and pausing must not cost you the ability to test.
    temporary = not rec.get("enabled")
    if temporary:
        write_plist(rec)
        bootstrap(rid)
    # Marker first, then kickstart: the runner consumes it to label the run
    # "manual". Written before firing because the job can start immediately.
    md = _mkdir_private(runs_dir() / rid)
    try:
        (md / ".manual").write_text(now_iso(), encoding="utf-8")
    except OSError:
        pass
    r = kickstart(rid)
    ok = r.returncode == 0
    if temporary:
        bootout(rid)
    return {"kickstarted": ok, "label": label_for(rid),
            "stderr": (r.stderr or "").strip() or None,
            # kickstart ignores launch conditions, so a green run here proves the
            # runner and the prompt -- NOT that the schedule fires.
            "note": "Started. This runs it regardless of its schedule, so it "
                    "proves the routine works — not that the schedule fires."}


def orphans():
    """Loaded jobs / plists with no record behind them. macOS has no uninstall
    hook, so these are the residue of a deleted app or a failed delete."""
    have = set(list_ids())
    out = []
    d = agents_dir()
    if d.is_dir():
        for p in d.glob(LABEL_PREFIX + "*.plist"):
            rid = p.stem[len(LABEL_PREFIX):]
            if rid not in have:
                out.append({"id": rid, "plist": str(p),
                            "loaded": job_state(rid)["loaded"]})
    return out


def reconcile(fix=False):
    found = orphans()
    fixed = []
    if fix:
        for o in found:
            bootout(o["id"])
            try:
                Path(o["plist"]).unlink()
                fixed.append(o["id"])
            except OSError:
                pass
    return {"orphans": found, "fixed": fixed}


def heartbeat():
    try:
        _mkdir_private(store_dir())
        _write_private(store_dir() / ".heartbeat", now_iso())
    except OSError:
        pass


def state():
    """Everything the screen needs, in one read."""
    heartbeat()
    out = []
    for rid in list_ids():
        try:
            rec = load(rid)
        except (ValueError, OSError) as exc:
            out.append({"id": rid, "unreadable": str(exc)})
            continue
        js = job_state(rid)
        rr = runs(rid, limit=1)
        last = rr["runs"][0] if rr["runs"] else None
        out.append({
            "id": rid, "description": rec["description"], "prompt": rec["prompt"],
            "cwd": rec["cwd"], "cwd_exists": os.path.isdir(rec["cwd"]),
            "model": rec["model"], "permission_mode": rec["permission_mode"],
            "schedule": rec["schedule"], "enabled": rec["enabled"],
            "opts": rec.get("opts") or {},
            "created_at": rec.get("created_at"), "updated_at": rec.get("updated_at"),
            "auto_disabled": rec.get("auto_disabled"),
            "loaded": js["loaded"], "last_exit_status": js["last_exit_status"],
            "total_runs": rr["total"], "never_run": rr["never_run"],
            "last_run": last,
            # A green manual run does not prove the schedule works. Say which.
            "never_fired_on_schedule": rr["total"] > 0 and not any(
                r.get("trigger") == "schedule" for r in runs(rid, limit=200)["runs"]),
        })
    return {
        "read_at": now_iso(),
        "store": str(store_dir()),
        "runs_store": str(runs_dir()),
        "runner_installed": runner_path().is_file(),
        "runner_sha": runner_sha(),
        "permission_modes": list(ROUTINE_PERMISSION_MODES),
        "models": list(MODELS),
        "presets": list(PRESETS),
        "routines": out,
        "orphans": orphans(),
        # Stated on the screen, not buried: this is the sharp edge of local scheduling.
        "note": "It must be awake and logged in. "
                "If it is asleep at the scheduled time launchd runs the job on "
                "wake — and several missed slots are coalesced into ONE run, "
                "not one per slot.",
    }
