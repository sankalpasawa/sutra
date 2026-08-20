#!/usr/bin/env python3
"""Live device-flow connect. The P1 end-to-end path against real GitHub.

    python3 bin/connect.py connect [--label work]
    python3 bin/connect.py list
    python3 bin/connect.py whoami <connector_id>
    python3 bin/connect.py disconnect <connector_id>

State: ~/.sutra/connectors.db (0600) + the macOS Keychain. No token ever
touches the database and no client secret exists to leak.
"""
import argparse
import os
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from connectors.config import ProviderConfig                      # noqa: E402
from connectors.credentials import KeychainCredentialStore, keychain_available  # noqa: E402
from connectors.credentials.store import MemoryCredentialStore    # noqa: E402
from connectors.database import Database                          # noqa: E402
from connectors.errors import AuthorizationPending, ConnectorError, SlowDown  # noqa: E402
from connectors.service import ConnectorService                   # noqa: E402

DB_PATH = os.path.expanduser("~/.sutra/connectors.db")
OPERATOR = os.environ.get("SUTRA_OPERATOR", "local")


def build_service():
    db = Database(DB_PATH)
    db.migrate()
    if not keychain_available():
        print("! Keychain unavailable; credentials will NOT persist.", file=sys.stderr)
        store = MemoryCredentialStore()
    else:
        store = KeychainCredentialStore()
    return db, ConnectorService(db, store, config=ProviderConfig.from_env())


def cmd_connect(service, args):
    started = service.begin_connect(OPERATOR, label=args.label)
    print()
    print("  1. Your code:  %s" % started["user_code"])
    print("  2. Open:       %s" % started["verification_uri"])
    print("  3. Enter the code and approve.")
    print()
    if not args.no_browser:
        webbrowser.open(started["verification_uri"])

    interval = started.get("poll_interval_seconds", 5)
    deadline = time.time() + 900
    while time.time() < deadline:
        time.sleep(interval)
        try:
            result = service.poll_connect(OPERATOR, started["transaction_id"])
        except (AuthorizationPending, SlowDown):
            continue
        except ConnectorError as exc:
            print("  x %s: %s" % (exc.code, exc.message))
            return 1
        if result.get("status") == "COMPLETED":
            account = result["connector"]["account"]
            print("  ok connected as %s (id %s)" % (account["username"], account["id"]))
            print("     connector: %s" % result["connector_id"])
            return 0
        interval = result.get("poll_interval_seconds", interval)
        sys.stdout.write("."); sys.stdout.flush()
    print("  x timed out")
    return 1


def cmd_begin(service, args):
    """Open a transaction and print the code, then exit.

    `connect` blocks in a poll loop, which hides the code from anything driving
    this non-interactively. begin/poll splits it so the code is surfaced the
    moment GitHub issues it.
    """
    started = service.begin_connect(OPERATOR, label=args.label)
    print("USER_CODE=%s" % started["user_code"])
    print("VERIFICATION_URI=%s" % started["verification_uri"])
    print("TRANSACTION_ID=%s" % started["transaction_id"])
    print("EXPIRES_AT=%s" % started["expires_at"])
    print("POLL_INTERVAL=%s" % started.get("poll_interval_seconds", 5))
    if args.open:
        webbrowser.open(started["verification_uri"])
    return 0


def cmd_poll(service, args):
    """Poll one transaction to completion. Honours GitHub's interval."""
    interval = args.interval
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            result = service.poll_connect(OPERATOR, args.transaction_id)
        except (AuthorizationPending, SlowDown):
            time.sleep(interval)
            continue
        except ConnectorError as exc:
            print("ERROR=%s MESSAGE=%s" % (exc.code, exc.message))
            return 1
        if result.get("status") == "COMPLETED":
            account = result["connector"]["account"]
            print("STATUS=COMPLETED")
            print("CONNECTOR_ID=%s" % result["connector_id"])
            print("ACCOUNT_ID=%s" % account["id"])
            print("USERNAME=%s" % account["username"])
            print("DISPLAY_NAME=%s" % account.get("display_name"))
            return 0
        interval = result.get("poll_interval_seconds", interval)
        time.sleep(interval)
    print("ERROR=TIMEOUT")
    return 1


def cmd_list(service, args):
    rows = service.list_connectors(OPERATOR)
    if not rows:
        print("  no connectors. run: connect")
        return 0
    for row in rows:
        print("  %s  %-12s %-22s %s" % (
            "*" if row["status"] == "ACTIVE" else "!",
            row["status"], "@" + row["account"]["username"], row["id"]))
    return 0


def cmd_repos(service, args):
    result = service.list_repositories(OPERATOR, args.connector_id,
                                       cursor=args.cursor, refresh=args.refresh)
    rows = result["repositories"]
    if not rows:
        print("  no repositories — %s" % result.get("empty_reason"))
        if result.get("install_url"):
            print("  install Sutra on an account: %s" % result["install_url"])
        elif result.get("user_action") == "ADD_REPOSITORY":
            print("  the installation exists but selects no repositories.")
            print("  add some: https://github.com/settings/installations")
        return 0
    print("  %-38s %-9s %-7s %s" % ("REPOSITORY", "VIS", "PERM", "CAPABILITIES"))
    for r in rows:
        print("  %-38s %-9s %-7s %d" % (r["full_name"], r["visibility"],
                                        r["user_permission"], len(r["capabilities"])))
        if args.verbose:
            for cap in r["capabilities"]:
                print("      %s" % cap)
    if result.get("next_cursor"):
        print("  more: --cursor %s" % result["next_cursor"])
    return 0


def cmd_orgs(service, args):
    result = service.list_organizations(OPERATOR, args.connector_id, refresh=args.refresh)
    personal = result.get("personal_installation")
    if personal:
        print("  * %-22s installed, %s repos" % (personal["account"],
                                                 personal["repository_selection"]))
    for o in result["organizations"]:
        mark = {"ok": "*", "not_installed": "o", "sso_required": "!",
                "suspended": "!"}.get(o["access"], "?")
        note = {"ok": "installed", "not_installed": "Sutra not installed",
                "sso_required": "SAML sign-in required",
                "suspended": "installation suspended"}.get(o["access"], o["access"])
        print("  %s %-22s %s" % (mark, o["login"], note))
    if not result["organizations"] and not personal:
        print("  no organizations, and Sutra is not installed anywhere.")
    return 0


def cmd_installations(service, args):
    for i in service.sync_installations(OPERATOR, args.connector_id):
        print("  id=%-6s %-20s %-14s repos=%s" % (
            i.installation_id, i.account_login, i.account_type, i.repository_selection))
        for resource, level in sorted(i.permissions.items()):
            print("      %-18s %s" % (resource, level))
    return 0


def cmd_whoami(service, args):
    print("  %s" % service.validate(OPERATOR, args.connector_id))
    return 0


def cmd_disconnect(service, args):
    result = service.disconnect(OPERATOR, args.connector_id)
    print("  credentials deleted: %s" % result["credentials_deleted"])
    print("  revoked on GitHub  : %s" % result["provider_authorization_revoked"])
    if not result["provider_authorization_revoked"]:
        print("  to also revoke Sutra's authorization on GitHub:")
        print("    %s" % result["revoke_instructions_url"])
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("connect"); p.add_argument("--label"); p.add_argument(
        "--no-browser", action="store_true"); p.set_defaults(fn=cmd_connect)
    p = sub.add_parser("begin"); p.add_argument("--label")
    p.add_argument("--open", action="store_true"); p.set_defaults(fn=cmd_begin)
    p = sub.add_parser("poll"); p.add_argument("transaction_id")
    p.add_argument("--interval", type=int, default=5)
    p.add_argument("--timeout", type=int, default=870); p.set_defaults(fn=cmd_poll)
    p = sub.add_parser("list"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("repos"); p.add_argument("connector_id")
    p.add_argument("--cursor"); p.add_argument("--refresh", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true"); p.set_defaults(fn=cmd_repos)
    p = sub.add_parser("orgs"); p.add_argument("connector_id")
    p.add_argument("--refresh", action="store_true"); p.set_defaults(fn=cmd_orgs)
    p = sub.add_parser("installations"); p.add_argument("connector_id")
    p.set_defaults(fn=cmd_installations)
    p = sub.add_parser("whoami"); p.add_argument("connector_id"); p.set_defaults(fn=cmd_whoami)
    p = sub.add_parser("disconnect"); p.add_argument("connector_id")
    p.set_defaults(fn=cmd_disconnect)
    args = parser.parse_args()
    db, service = build_service()
    try:
        return args.fn(service, args)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
