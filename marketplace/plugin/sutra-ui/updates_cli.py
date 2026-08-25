"""updates_cli.py -- the desktop update machinery, callable without HTTP.

WHY THIS EXISTS. The Electron shell attaches to any Sutra already serving the
pinned port (a CLI or source-checkout uvicorn). In attach mode the shell holds
no control token for that foreign backend, so every token-authenticated update
route is unreachable -- and for CLI-habit users the installed app silently
never self-updated. The machinery itself (updates.py) never needed the server:
it is stdlib-only, nothing runs on import, and every operation is a plain
function. This shim exposes exactly those functions to the shell as a spawned
child process.

NO TOKEN, ON PURPOSE. The desktop token exists because any browser page can
POST to localhost. A child process spawned by the signed shell is not
reachable from a web page; adding a token here would protect nothing.

CONTRACT. One verb per invocation. A JSON object on stdout and exit 0 on
success; {"error": "<reason>"} on stdout and exit 1 on a refusal or failure.
Nothing else is printed to stdout -- the shell parses it.

Run as:  <bundle-python> -m updates_cli <verb> [args]
   with  cwd = the sutra-ui payload directory (puts updates.py on sys.path;
         asserted below because a wrong cwd would otherwise surface as a
         confusing packaging failure), PYTHONDONTWRITEBYTECODE=1 (the signed
         bundle is read-only).

Verbs:
  check                     network: latest release vs this bundle (all_state)
  staged                    network-free: staging manifest state (quit-safe)
  stage                     network: download+verify the newest release
  arm --wait-pid N [--wait-start S] [--relaunch]
                            schedule the swap after pid N exits
  resolve [--installed V]   launch-time reconciliation of the last attempt
"""
import argparse
import json
import os
import sys

if not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(__file__)), "updates.py")):
    print(json.dumps({"error": "updates_cli must live beside updates.py"}))
    sys.exit(1)

import updates  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(prog="updates_cli", add_help=True)
    sub = ap.add_subparsers(dest="verb", required=True)
    sub.add_parser("check")
    sub.add_parser("staged")
    sub.add_parser("stage")
    arm = sub.add_parser("arm")
    arm.add_argument("--wait-pid", type=int, required=True)
    arm.add_argument("--wait-start", type=float, default=None)
    arm.add_argument("--relaunch", action="store_true")
    res = sub.add_parser("resolve")
    res.add_argument("--installed", default=None)
    ns = ap.parse_args(argv)

    try:
        if ns.verb == "check":
            out = updates.all_state()
        elif ns.verb == "staged":
            out = updates.pending_state()
        elif ns.verb == "stage":
            out = updates.stage_desktop()
        elif ns.verb == "arm":
            out = updates.arm_desktop(ns.wait_pid, wait_start=ns.wait_start,
                                      relaunch=ns.relaunch)
        else:
            out = updates.resolve_pending(installed_version=ns.installed)
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
