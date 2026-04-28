#!/usr/bin/env python3
"""
Sutra project-state utility — replaces python3 stdin heredocs in start.sh
and onboard.sh.

Background — vinit#38 (filed 2026-04-28, on behalf of @abhishekshah):
    On certain macOS setups (Endpoint Security agents, MDM/EDR, sandbox-
    exec wrappers), python3 invocations of the form `python3 - <<'PY'`
    receive SIGKILL (exit 137) mid-execution while bash code paths run
    fine. The kill is external; the script cannot intercept. Result:
    0-byte sutra-project.json + partial governance block + bricked
    /core:start.

Fix per Vinit recommendation A (replace heredocs with file form): all
python3 logic lives in this real .py file. `python3 path/to/file.py
<subcmd>` is much less likely to be flagged by sandbox / EDR than the
heredoc-via-stdin form.

Atomic writes (Vinit recommendation C): every file mutation goes
through tempfile + os.replace, so a mid-write SIGKILL leaves the
prior valid file content untouched rather than producing a 0-byte
corrupted file.

Subcommands:
    patch-profile <profile> <telemetry_default 0|1>
        Patch .claude/sutra-project.json: set profile + telemetry_optin.
        Used by start.sh after onboard.

    write-onboard <install_id> <project_id> <name> <first_seen>
                  <version> <optin_str> <existing_identity_json>
        Initial onboard write of .claude/sutra-project.json (atomic).
        Used by onboard.sh.

    stamp-identity <identity_json>
        Stamp identity block into existing .claude/sutra-project.json
        (atomic). Used by onboard.sh post-consent path. Best-effort:
        any failure exits 0 silently per onboard.sh contract.

    banner
        Print /core:start activation banner. Used by start.sh.
"""
import json
import os
import shutil
import sys
import tempfile

PROJECT_JSON = ".claude/sutra-project.json"


def atomic_write(path, content):
    """Write content to path atomically: tempfile in same dir + os.replace.

    A SIGKILL between create-tempfile and os.replace leaves the original
    file intact. A SIGKILL after os.replace means the new content is on
    disk and the tempfile is already gone. Either way, we never have a
    half-written target file.
    """
    target_dir = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=target_dir, prefix=".sutra-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cmd_patch_profile(profile, telemetry_default):
    if not os.path.exists(PROJECT_JSON):
        print(f"-- {PROJECT_JSON} missing; skipping patch", file=sys.stderr)
        return 0
    try:
        with open(PROJECT_JSON) as f:
            d = json.load(f)
    except json.JSONDecodeError:
        print(f"-- {PROJECT_JSON} is empty or corrupt; cannot patch", file=sys.stderr)
        print(f"   recover: rm {PROJECT_JSON} && /core:start", file=sys.stderr)
        return 2
    d["profile"] = profile
    d["telemetry_optin"] = telemetry_default == "1"
    atomic_write(PROJECT_JSON, json.dumps(d, indent=2))
    return 0


def cmd_write_onboard(install_id, project_id, name, first_seen, version, optin_str, existing_identity):
    d = {
        "install_id": install_id,
        "project_id": project_id,
        "project_name": name,
        "first_seen": first_seen,
        "sutra_version": version,
        "telemetry_optin": optin_str == "true",
    }
    if existing_identity:
        try:
            d["identity"] = json.loads(existing_identity)
        except json.JSONDecodeError:
            pass
    # ensure parent dir exists (caller does mkdir -p .claude already, but be safe)
    parent = os.path.dirname(os.path.abspath(PROJECT_JSON))
    if not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    atomic_write(PROJECT_JSON, json.dumps(d, indent=2))
    return 0


def cmd_stamp_identity(identity_json):
    try:
        with open(PROJECT_JSON) as f:
            d = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0  # best-effort per onboard.sh contract
    try:
        d["identity"] = json.loads(identity_json)
    except json.JSONDecodeError:
        return 0
    atomic_write(PROJECT_JSON, json.dumps(d, indent=2))
    return 0


def cmd_banner():
    try:
        with open(PROJECT_JSON) as f:
            d = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print("-- onboard failed — sutra-project.json missing or corrupt", file=sys.stderr)
        return 1

    print("🧭 Sutra active")
    print(f"   Version:         {d.get('sutra_version', 'unknown')}")
    print(f"   Project:         {d.get('project_name', '<unnamed>')}")
    print(f"   Install ID:      {d.get('install_id', '<missing>')}")
    print(f"   Project ID:      {d.get('project_id', '<missing>')}")
    print(f"   Profile:         {d.get('profile', 'project')}")

    if d.get("telemetry_optin") and os.environ.get("SUTRA_LEGACY_TELEMETRY") == "1":
        tel = "on — legacy push active (SUTRA_LEGACY_TELEMETRY=1)"
    elif d.get("telemetry_optin"):
        tel = "local-only — push disabled in v2.0 privacy model (see PRIVACY.md)"
    else:
        tel = "off"
    print(f"   Telemetry:       {tel}")

    rtk_active = (
        shutil.which("rtk") is not None
        and not os.path.exists(os.path.expanduser("~/.rtk-disabled"))
    )
    print(
        f"   RTK rewrite:     {'active' if rtk_active else 'inactive — rtk binary not installed (opt-in; see README)'}"
    )
    print()
    print("   Skills loaded:   input-routing, depth-estimation, readability-gate, output-trace")
    profile = d.get("profile", "project")
    enforcement = (
        "HARD — missing depth marker blocks Edit/Write"
        if profile == "company"
        else "warn-only"
    )
    print(f"   Enforcement:     {enforcement}")
    print()
    print("You're ready. Ask Claude anything — every task goes through governance.")
    print()
    print("Other commands:")
    print("   /core:status      — show install / queue / telemetry state")
    print("   /core:update      — pull the latest plugin version")
    print("   /core:uninstall   — remove Sutra from this machine")
    print("   /core:depth-check — manual depth marker for the next task")
    print("   /core:permissions — paste-ready allowlist snippet")
    if profile == "company":
        print()
        print("Escape hatch (one-shot): prefix any tool call with SUTRA_BYPASS=1")
    return 0


HANDLERS = {
    "patch-profile": cmd_patch_profile,
    "write-onboard": cmd_write_onboard,
    "stamp-identity": cmd_stamp_identity,
    "banner": cmd_banner,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in HANDLERS:
        print(
            "usage: _sutra_project_lib.py <subcmd> [args...]\n"
            f"  subcmds: {', '.join(HANDLERS)}",
            file=sys.stderr,
        )
        return 2
    cmd = sys.argv[1]
    args = sys.argv[2:]
    try:
        return HANDLERS[cmd](*args) or 0
    except TypeError as e:
        print(f"argument error in {cmd}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
