#!/usr/bin/env python3
"""sessions — unified Claude Code session tool.

Subcommands:
  dash                  render dashboard markdown + chat-view summary
  pick [QUERY]          fuzzy-pick a session and resume (was: sresume)
  list [N]              flat list of recent sessions, no resume
  resume <ID-OR-NAME>   directly resume a session by id-prefix or bookmark
  last                  resume the most recent session (alias for `claude -c`)
  bookmark <NAME> [ID]  save a bookmark (defaults to most recent session id)
  unbookmark <NAME>     remove a bookmark
  schedule install      install daily 08:00 launchd job (macOS) / cron line (Linux)
  schedule uninstall    remove the launchd job
  schedule status       show current schedule state
  --help / -h           print help

No subcommand: smart default — `dash` when stdout is not a tty (e.g. slash
command), `pick` when stdout is a tty (interactive terminal use).

Common flags (apply where relevant): --here, --top N, --no-write, --output PATH
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ----- paths / constants ------------------------------------------------

HOME = Path.home()
PROJECTS_DIR = HOME / ".claude" / "projects"
BOOKMARKS = HOME / ".sutra" / "bookmarks.jsonl"
DEFAULT_OUTPUT = HOME / "session-dashboard.md"
SCAN_LIMIT = 50  # cap rows shown by pick / list

LAUNCHD_LABEL = "com.user.claude-sessions-dashboard"
LAUNCHD_PLIST = HOME / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"

# Sutra/Claude bootstrap noise — skipped when extracting session titles
BOOTSTRAP_RE = re.compile(
    r"(/core:(start|status|update|sbom|permissions|uninstall|depth-check)"
    r"|^Run /core:"
    r"|^User (ran|invoked) /core:"
    r"|activate Sutra"
    r"|initialize Sutra)",
    re.IGNORECASE,
)


# ----- transcript parsing ----------------------------------------------

def encode_cwd(cwd: Path) -> str:
    return "-" + str(cwd).lstrip("/").replace("/", "-")


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for c in content:
        if not isinstance(c, dict):
            continue
        t = c.get("type")
        if t == "text":
            parts.append(c.get("text", ""))
        elif t == "tool_use":
            name = c.get("name", "?")
            inp = c.get("input") or {}
            hint = inp.get("command") or inp.get("file_path") or inp.get("description") or ""
            parts.append(f"[tool:{name} {str(hint)[:60]}]" if hint else f"[tool:{name}]")
        elif t == "tool_result":
            r = c.get("content", "")
            if isinstance(r, list):
                r = " ".join(p.get("text", "") for p in r if isinstance(p, dict))
            parts.append(f"[result: {str(r)[:80]}]")
    return " ".join(p for p in parts if p).strip()


def scan_session(path: Path):
    """Full scan for the dashboard view: last user, last assistant, blockers."""
    last_user = None
    last_assistant = None
    cwd = None
    rate_limited = False
    api_error = None
    line_count = 0
    first_ts = None

    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                line_count += 1
                if not cwd and obj.get("cwd"):
                    cwd = obj["cwd"]
                ts = obj.get("timestamp")
                if ts and not first_ts:
                    first_ts = ts
                t = obj.get("type")
                if t == "user":
                    msg = obj.get("message") or {}
                    text = extract_text(msg.get("content", ""))
                    if text and not text.lstrip().startswith("[result:"):
                        last_user = (ts, text)
                elif t == "assistant":
                    msg = obj.get("message") or {}
                    text = extract_text(msg.get("content", []))
                    if text:
                        last_assistant = (ts, text)
                    if obj.get("error") == "rate_limit":
                        rate_limited = True
                    if obj.get("isApiErrorMessage"):
                        api_error = obj.get("apiErrorStatus") or "api-error"
    except OSError:
        return None

    return {
        "path": path,
        "cwd": cwd or "?",
        "session_id": path.stem,
        "mtime": path.stat().st_mtime,
        "first_ts": first_ts,
        "last_user": last_user,
        "last_assistant": last_assistant,
        "rate_limited": rate_limited,
        "api_error": api_error,
        "line_count": line_count,
    }


def extract_title(path: Path) -> str:
    """Lightweight title extraction for pick / list (used to be in sresume)."""
    bootstrap_title = None
    real_title = None
    fallback_title = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = o.get("message") or {}
                c = msg.get("content", "")
                text = ""
                if isinstance(c, str):
                    text = c
                elif isinstance(c, list):
                    text = "\n".join(
                        p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                if not text:
                    continue
                m = re.search(r"^INPUT:\s*(.+)$", text, re.MULTILINE)
                if m:
                    candidate = m.group(1).strip()
                    if bootstrap_title is None:
                        bootstrap_title = candidate
                    if real_title is None and not BOOTSTRAP_RE.search(candidate):
                        real_title = candidate
                        break
                if fallback_title is None and o.get("type") == "user":
                    s = text.strip()
                    if (s and not s.startswith("<")
                            and not s.startswith("# /core:")
                            and not BOOTSTRAP_RE.search(s)):
                        fallback_title = " ".join(s.split())
    except OSError:
        pass
    return (real_title or fallback_title or bootstrap_title or "<untitled>")[:90]


def collect_sessions(here: bool = False, full: bool = True):
    """List sessions sorted by mtime desc. full=True does the dashboard scan;
    full=False does only the lightweight metadata + lazy title."""
    if not PROJECTS_DIR.exists():
        return []
    target = encode_cwd(Path.cwd()) if here else None
    sessions = []
    for proj_dir in PROJECTS_DIR.iterdir():
        if not proj_dir.is_dir():
            continue
        if target and proj_dir.name != target:
            continue
        for f in proj_dir.glob("*.jsonl"):
            if full:
                s = scan_session(f)
                if s:
                    sessions.append(s)
            else:
                try:
                    sessions.append({
                        "session_id": f.stem,
                        "mtime": f.stat().st_mtime,
                        "path": f,
                        "cwd": proj_dir.name,
                    })
                except OSError:
                    continue
    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    return sessions


# ----- bookmarks --------------------------------------------------------

def load_bookmarks() -> dict[str, str]:
    """Return {bookmark_name: session_id}."""
    if not BOOKMARKS.exists():
        return {}
    bm = {}
    try:
        with open(BOOKMARKS, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                    if o.get("name") and o.get("session_id"):
                        bm[o["name"]] = o["session_id"]
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return bm


def save_bookmark(name: str, session_id: str) -> None:
    BOOKMARKS.parent.mkdir(parents=True, exist_ok=True)
    # Read existing, replace or append
    existing = []
    if BOOKMARKS.exists():
        for line in BOOKMARKS.read_text().splitlines():
            try:
                o = json.loads(line)
                if o.get("name") != name:
                    existing.append(o)
            except json.JSONDecodeError:
                continue
    existing.append({
        "name": name,
        "session_id": session_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    BOOKMARKS.write_text("\n".join(json.dumps(e) for e in existing) + "\n")


def remove_bookmark(name: str) -> bool:
    if not BOOKMARKS.exists():
        return False
    kept = []
    removed = False
    for line in BOOKMARKS.read_text().splitlines():
        try:
            o = json.loads(line)
            if o.get("name") == name:
                removed = True
                continue
            kept.append(o)
        except json.JSONDecodeError:
            continue
    BOOKMARKS.write_text("\n".join(json.dumps(e) for e in kept) + ("\n" if kept else ""))
    return removed


# ----- blockers + formatting ------------------------------------------

def detect_blocker(s, age_seconds):
    if s.get("rate_limited"):
        return "rate-limit"
    if s.get("api_error"):
        return f"api-error {s['api_error']}"
    asst = (s.get("last_assistant") or (None, ""))[1] or ""
    asst_low = asst.lower()
    tail = asst_low[-400:]
    if re.search(r"permission[s]? denied|denied the tool|tool .* was denied", tail):
        return "perm-denied"
    if re.search(r"\bwaiting (on|for|until)\b|\bblocked on\b|\bcan you (provide|share|confirm|paste)\b", tail):
        return "needs-input"
    last_line = (asst.strip().splitlines() or [""])[-1].strip()
    if last_line.endswith("?"):
        return "open-question"
    if re.search(r"\btraceback\b|\bexception\b", tail):
        return "error"
    if age_seconds > 7 * 86400:
        return "stale"
    return "—"


def humanize_age(seconds: float) -> str:
    if seconds < 60:
        return "now"
    if seconds < 3600:
        return f"{int(seconds/60)}m"
    if seconds < 86400:
        return f"{int(seconds/3600)}h"
    return f"{int(seconds/86400)}d"


def truncate(s: str, n: int = 110) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def resume_command(session_id: str, bookmark: str | None) -> str:
    if bookmark:
        return f"sessions resume {bookmark}"
    return f"sessions resume {session_id[:8]}"


# ----- subcommand: dash ------------------------------------------------

def render_markdown(sessions, bookmarks_by_uuid, now) -> str:
    lines = []
    lines.append("# Claude Code Session Dashboard")
    lines.append("")
    by_proj = {}
    for s in sessions:
        by_proj.setdefault(s["cwd"], []).append(s)
    lines.append(
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        f"{len(sessions)} sessions across {len(by_proj)} project(s)_"
    )
    lines.append("")

    buckets = {"<1h": 0, "1-24h": 0, "1-7d": 0, ">7d": 0}
    blocker_counts: dict[str, int] = {}
    for s in sessions:
        age = now - s["mtime"]
        if age < 3600:
            buckets["<1h"] += 1
        elif age < 86400:
            buckets["1-24h"] += 1
        elif age < 7 * 86400:
            buckets["1-7d"] += 1
        else:
            buckets[">7d"] += 1
        b = detect_blocker(s, age)
        blocker_counts[b] = blocker_counts.get(b, 0) + 1

    lines.append("## Summary")
    lines.append("")
    lines.append("| Idle bucket | Count |")
    lines.append("|---|---|")
    for k, v in buckets.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("| Blocker tag | Count |")
    lines.append("|---|---|")
    for k, v in sorted(blocker_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {k} | {v} |")
    lines.append("")

    flagged = [s for s in sessions if detect_blocker(s, now - s["mtime"]) != "—"]
    if flagged:
        lines.append("## Flagged sessions (blocked / open / errored / stale)")
        lines.append("")
        lines.append("| Idle | Project | Blocker | Last instruction | Last reply | Resume |")
        lines.append("|---|---|---|---|---|---|")
        for s in flagged[:50]:
            age = now - s["mtime"]
            blocker = detect_blocker(s, age)
            lu = (s["last_user"] or (None, "(none)"))[1]
            la = (s["last_assistant"] or (None, "(none)"))[1]
            cmd = resume_command(s["session_id"], bookmarks_by_uuid.get(s["session_id"]))
            lines.append(
                f"| {humanize_age(age)} | `{md_escape(s['cwd'])}` | **{blocker}** | "
                f"{md_escape(truncate(lu, 80))} | {md_escape(truncate(la, 80))} | "
                f"`{cmd}` |"
            )
        lines.append("")

    lines.append("## Sessions by project")
    lines.append("")
    for proj in sorted(by_proj.keys(), key=lambda p: -max(s["mtime"] for s in by_proj[p])):
        ps = by_proj[proj]
        ps.sort(key=lambda s: s["mtime"], reverse=True)
        lines.append(f"### `{proj}` — {len(ps)} session(s)")
        lines.append("")
        lines.append("| Idle | Blocker | Lines | Last instruction | Last reply | Resume |")
        lines.append("|---|---|---|---|---|---|")
        for s in ps:
            age = now - s["mtime"]
            blocker = detect_blocker(s, age)
            lu = (s["last_user"] or (None, "(none)"))[1]
            la = (s["last_assistant"] or (None, "(none)"))[1]
            cmd = resume_command(s["session_id"], bookmarks_by_uuid.get(s["session_id"]))
            lines.append(
                f"| {humanize_age(age)} | {blocker} | {s['line_count']} | "
                f"{md_escape(truncate(lu, 75))} | {md_escape(truncate(la, 75))} | "
                f"`{cmd}` |"
            )
        lines.append("")

    lines.append("## Detail — 15 most recent sessions")
    lines.append("")
    for s in sessions[:15]:
        age = now - s["mtime"]
        cmd = resume_command(s["session_id"], bookmarks_by_uuid.get(s["session_id"]))
        lines.append(f"#### `{s['session_id'][:8]}` · {s['cwd']} · idle {humanize_age(age)}")
        lines.append("")
        lines.append(f"- **Blocker:** {detect_blocker(s, age)}")
        lines.append(f"- **Resume:** `{cmd}`")
        lines.append(f"- **Session id:** `{s['session_id']}`")
        lines.append(f"- **Lines:** {s['line_count']}")
        if s["last_user"]:
            ts, text = s["last_user"]
            lines.append(f"- **Last instruction** _({ts})_:")
            lines.append(f"  > {truncate(text, 500)}")
        if s["last_assistant"]:
            ts, text = s["last_assistant"]
            lines.append(f"- **Last reply** _({ts})_:")
            lines.append(f"  > {truncate(text, 500)}")
        lines.append("")

    return "\n".join(lines)


def render_chat_view(sessions, bookmarks_by_uuid, now, top_n: int) -> str:
    lines = []
    by_proj = {}
    for s in sessions:
        by_proj.setdefault(s["cwd"], []).append(s)
    lines.append(f"## Session dashboard — {len(sessions)} sessions, {len(by_proj)} project(s)")
    lines.append("")

    flagged = [s for s in sessions if detect_blocker(s, now - s["mtime"]) != "—"]
    if flagged:
        lines.append(f"### Flagged ({len(flagged)})")
        lines.append("")
        lines.append("| Idle | Blocker | Last instruction | Resume |")
        lines.append("|---|---|---|---|")
        for s in flagged[:top_n]:
            age = now - s["mtime"]
            lu = (s["last_user"] or (None, "(none)"))[1]
            cmd = resume_command(s["session_id"], bookmarks_by_uuid.get(s["session_id"]))
            lines.append(
                f"| {humanize_age(age)} | **{detect_blocker(s, age)}** | "
                f"{md_escape(truncate(lu, 70))} | `{cmd}` |"
            )
        lines.append("")
    else:
        lines.append("_No flagged sessions._")
        lines.append("")

    lines.append(f"### Most recent ({min(top_n, len(sessions))} of {len(sessions)})")
    lines.append("")
    lines.append("| Idle | Project | Last instruction | Resume |")
    lines.append("|---|---|---|---|")
    for s in sessions[:top_n]:
        age = now - s["mtime"]
        lu = (s["last_user"] or (None, "(none)"))[1]
        cmd = resume_command(s["session_id"], bookmarks_by_uuid.get(s["session_id"]))
        proj = s["cwd"].rsplit("/", 1)[-1] or s["cwd"]
        lines.append(
            f"| {humanize_age(age)} | `{md_escape(proj)}` | "
            f"{md_escape(truncate(lu, 70))} | `{cmd}` |"
        )
    return "\n".join(lines)


def cmd_dash(args) -> int:
    sessions = collect_sessions(here=args.here, full=True)
    quiet = args.no_write_stdout
    if not sessions:
        msg = "_No Claude Code sessions found._"
        if not args.no_write:
            args.output.write_text(f"# Claude Code Session Dashboard\n\n{msg}\n")
        if not quiet:
            print(msg)
        return 0
    bm = load_bookmarks()
    bookmarks_by_uuid = {sid: name for name, sid in bm.items()}
    now = time.time()
    if not args.no_write:
        md = render_markdown(sessions, bookmarks_by_uuid, now)
        args.output.write_text(md)
    if not quiet:
        chat = render_chat_view(sessions, bookmarks_by_uuid, now, args.top)
        print(chat)
        if not args.no_write:
            print(f"\n_Full report: `{args.output}`_")
    return 0


# ----- subcommand: pick / list / resume / last -------------------------

def do_resume(uuid: str) -> None:
    sys.stderr.write(f"\n→ claude --resume {uuid}\n\n")
    os.execvp("claude", ["claude", "--resume", uuid])


def render_pick_row(s, title: str, bookmark: str | None) -> str:
    bm = f"  [{bookmark}]" if bookmark else ""
    short = s["session_id"][:8]
    age = humanize_age(time.time() - s["mtime"])
    return f"{age:>4}  {short}  {title}{bm}"


def cmd_pick(args) -> int:
    sessions = collect_sessions(here=args.here, full=False)
    if not sessions:
        print("No sessions found.")
        return 0
    sessions = sessions[:SCAN_LIMIT]

    bookmarks = load_bookmarks()
    uuid_to_bookmark = {v: k for k, v in bookmarks.items()}

    # Exact bookmark match resumes immediately
    query = " ".join(args.query) if args.query else ""
    if query and query in bookmarks:
        do_resume(bookmarks[query])
        return 0

    rows = []
    for s in sessions:
        title = extract_title(s["path"])
        bm_name = uuid_to_bookmark.get(s["session_id"])
        rows.append((s, render_pick_row(s, title, bm_name)))

    if query:
        q = query.lower()
        rows = [(s, r) for s, r in rows if q in r.lower()]
        if not rows:
            print(f"No matches for '{query}'")
            return 1
        if len(rows) == 1:
            do_resume(rows[0][0]["session_id"])
            return 0

    # fzf if available
    try:
        proc = subprocess.run(
            ["fzf", "--height=50%", "--reverse", "--prompt=session> "],
            input="\n".join(r for _, r in rows),
            text=True, capture_output=True
        )
        if proc.returncode == 0 and proc.stdout.strip():
            picked = proc.stdout.strip()
            for s, r in rows:
                if r == picked:
                    do_resume(s["session_id"])
                    return 0
        return 0
    except FileNotFoundError:
        pass

    # Numbered fallback
    print("\nRecent Claude Code sessions:\n")
    shown = rows[:20]
    for i, (_, r) in enumerate(shown, 1):
        print(f"  {i:>2}. {r}")
    print()
    try:
        choice = input("Pick # (Enter to cancel): ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return 0
    if not choice:
        return 0
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(shown):
            do_resume(shown[idx][0]["session_id"])
    except ValueError:
        print(f"Invalid: {choice}")
    return 0


def cmd_list(args) -> int:
    sessions = collect_sessions(here=args.here, full=False)
    if not sessions:
        print("No sessions found.")
        return 0
    bookmarks = load_bookmarks()
    uuid_to_bookmark = {v: k for k, v in bookmarks.items()}
    n = args.n or 20
    for s in sessions[:n]:
        title = extract_title(s["path"])
        bm = uuid_to_bookmark.get(s["session_id"])
        print(render_pick_row(s, title, bm))
    return 0


def cmd_resume(args) -> int:
    target = args.target
    bookmarks = load_bookmarks()
    if target in bookmarks:
        do_resume(bookmarks[target])
        return 0
    # Match by id-prefix
    sessions = collect_sessions(full=False)
    matches = [s for s in sessions if s["session_id"].startswith(target)]
    if len(matches) == 1:
        do_resume(matches[0]["session_id"])
        return 0
    if len(matches) > 1:
        print(f"Ambiguous prefix '{target}' — {len(matches)} matches:")
        for s in matches[:10]:
            print(f"  {s['session_id']}")
        return 1
    print(f"No session matches '{target}' (not a bookmark, no id-prefix match).")
    return 1


def cmd_last(args) -> int:
    os.execvp("claude", ["claude", "-c"])


# ----- subcommand: bookmark / unbookmark -------------------------------

def cmd_bookmark(args) -> int:
    name = args.name
    if args.session_id:
        sid = args.session_id
        # Validate
        sessions = collect_sessions(full=False)
        match = [s for s in sessions if s["session_id"] == sid or s["session_id"].startswith(sid)]
        if not match:
            print(f"No session found matching '{sid}'.")
            return 1
        sid = match[0]["session_id"]
    else:
        sessions = collect_sessions(full=False)
        if not sessions:
            print("No sessions to bookmark.")
            return 1
        sid = sessions[0]["session_id"]
    save_bookmark(name, sid)
    print(f"Bookmark saved: '{name}' → {sid[:8]}")
    return 0


def cmd_unbookmark(args) -> int:
    if remove_bookmark(args.name):
        print(f"Removed bookmark '{args.name}'")
        return 0
    print(f"No bookmark named '{args.name}'")
    return 1


# ----- subcommand: schedule --------------------------------------------

def schedule_install() -> int:
    script_path = Path(__file__).resolve()
    if platform.system() != "Darwin":
        print("Auto-install only supported on macOS (launchd). For Linux, paste into crontab:\n")
        print(f"  0 8 * * * /usr/bin/env python3 {script_path} dash --no-write-stdout")
        return 0
    LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
    python_bin = shutil.which("python3") or "/usr/bin/python3"
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_bin}</string>
        <string>{script_path}</string>
        <string>dash</string>
        <string>--no-write-stdout</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{HOME}/Library/Logs/claude-sessions-dashboard.log</string>
    <key>StandardErrorPath</key>
    <string>{HOME}/Library/Logs/claude-sessions-dashboard.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""
    LAUNCHD_PLIST.write_text(plist)
    subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rc = subprocess.run(["launchctl", "load", str(LAUNCHD_PLIST)]).returncode
    if rc == 0:
        print(f"✓ Installed launchd job '{LAUNCHD_LABEL}' — fires daily at 08:00")
        print(f"  Plist: {LAUNCHD_PLIST}")
        print(f"  Logs:  ~/Library/Logs/claude-sessions-dashboard.log")
    else:
        print(f"✗ launchctl load returned {rc}; plist still written at {LAUNCHD_PLIST}")
    return rc


def schedule_uninstall() -> int:
    if platform.system() != "Darwin":
        print("Auto-uninstall only supported on macOS. Remove the cron line manually.")
        return 0
    if not LAUNCHD_PLIST.exists():
        print(f"No plist found at {LAUNCHD_PLIST}")
        return 0
    subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    LAUNCHD_PLIST.unlink()
    print(f"✓ Removed launchd job and plist {LAUNCHD_PLIST}")
    return 0


def schedule_status() -> int:
    if platform.system() != "Darwin":
        print("On Linux: check `crontab -l` for the dashboard line.")
        return 0
    if not LAUNCHD_PLIST.exists():
        print("Not installed.")
        return 0
    print(f"Plist: {LAUNCHD_PLIST}")
    out = subprocess.run(["launchctl", "list", LAUNCHD_LABEL],
                         capture_output=True, text=True)
    if out.returncode == 0:
        print("Status: loaded")
        print(out.stdout)
    else:
        print("Status: plist on disk but not loaded by launchctl")
    return 0


def cmd_schedule(args) -> int:
    if args.action == "install":
        return schedule_install()
    if args.action == "uninstall":
        return schedule_uninstall()
    return schedule_status()


# ----- argparse + smart default ---------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sessions",
        description="Unified Claude Code session tool — dashboard, picker, bookmarks, schedule.",
    )
    sub = p.add_subparsers(dest="cmd")

    p_dash = sub.add_parser("dash", help="render dashboard markdown + chat-view")
    p_dash.add_argument("--here", action="store_true",
                        help="filter to sessions started in the current cwd")
    p_dash.add_argument("--top", type=int, default=15,
                        help="rows in the chat-view summary (default 15)")
    p_dash.add_argument("--no-write", action="store_true",
                        help="don't write the markdown file, just print to stdout")
    p_dash.add_argument("--no-write-stdout", action="store_true",
                        help="(scheduler use) write the markdown file but skip stdout")
    p_dash.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"output markdown file (default {DEFAULT_OUTPUT})")
    p_dash.set_defaults(func=cmd_dash)

    p_pick = sub.add_parser("pick", help="fuzzy-pick a session and resume")
    p_pick.add_argument("query", nargs="*", help="optional fuzzy filter")
    p_pick.add_argument("--here", action="store_true")
    p_pick.set_defaults(func=cmd_pick)

    p_list = sub.add_parser("list", help="flat list of recent sessions, no resume")
    p_list.add_argument("n", nargs="?", type=int, default=20, help="how many rows (default 20)")
    p_list.add_argument("--here", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_res = sub.add_parser("resume", help="resume by id-prefix or bookmark name")
    p_res.add_argument("target")
    p_res.set_defaults(func=cmd_resume)

    p_last = sub.add_parser("last", help="resume the most recent session")
    p_last.set_defaults(func=cmd_last)

    p_bm = sub.add_parser("bookmark", help="save a bookmark name → session id")
    p_bm.add_argument("name")
    p_bm.add_argument("session_id", nargs="?",
                      help="session id (defaults to most recent)")
    p_bm.set_defaults(func=cmd_bookmark)

    p_ubm = sub.add_parser("unbookmark", help="remove a bookmark")
    p_ubm.add_argument("name")
    p_ubm.set_defaults(func=cmd_unbookmark)

    p_sch = sub.add_parser("schedule", help="manage daily-refresh launchd job")
    p_sch.add_argument("action", choices=["install", "uninstall", "status"])
    p_sch.set_defaults(func=cmd_schedule)

    return p


def smart_default(argv: list[str]) -> list[str]:
    """If no subcommand, pick one based on tty + argv shape."""
    known = {"dash", "pick", "list", "resume", "last", "bookmark",
             "unbookmark", "schedule", "-h", "--help"}
    if argv and argv[0] in known:
        return argv
    # No subcommand chosen — fall back based on tty
    if sys.stdout.isatty():
        return ["pick", *argv]
    return ["dash", *argv]


def main() -> int:
    argv = smart_default(sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
