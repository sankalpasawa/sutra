#!/usr/bin/env python3
"""mcp_allow_hook.py — let Sutra's own tools through the permission mode.

WHY THIS EXISTS, measured rather than assumed:

    claude -p --permission-mode plan ... --allowedTools 'mcp__sutra__*'
      -> permission_denials: [{'tool_name': 'mcp__sutra__sutra_routines_list'}]
         the MCP server is never called; the agent sees "Cannot call mcp..."

    The panel's DEFAULT mode is `plan` (providers.py DEFAULT_PERMISSION_MODE,
    app.py PERM_MODE), so without this the whole tool surface is denied 100% of
    the time in the shipped configuration -- a feature that looks implemented
    and never runs. `--allowedTools` does NOT fix it: the permission MODE is
    evaluated before allow rules.

    A PreToolUse hook IS evaluated before the mode, so it is the only mechanism
    that makes these tools reachable in `plan`.

WHY THAT IS SAFE HERE, and only here:

    This allows the mcp__sutra__* namespace and NOTHING else. It allows that
    namespace WHOLE -- any tool the sutra server offers -- which is safe only
    because build_agent_args passes --strict-mcp-config, so `sutra` is the one
    server the CLI loads and we are the only ones who can put a tool in it. If
    that flag ever comes off, this becomes a way in for any server that names
    itself `sutra`, and the flag and this hook must be removed together.

    No built-in tool is affected. Bash, Edit and Write keep the operator's
    chosen permission mode in full -- verified: with this hook installed and
    mode `plan`, asking the agent to Write a file still produced no file.

    And Sutra's own tools are safe to pre-allow because NONE OF THEM MUTATE:
    the read tools read, and the mutating-sounding ones write an inert proposal
    that changes nothing until a human clicks Approve in the panel. If that ever
    stops being true, this hook becomes a hole -- which is why a test asserts
    the tool surface contains no direct call into routines' write functions.

Reads a hook payload on stdin, writes a decision on stdout. Stdlib only.
"""
import json
import re
import sys

#: Anchored on purpose. `startswith` would also match a server that named
#: itself `sutra_evil`, and an unanchored search would match anywhere.
ALLOW = re.compile(r"^mcp__sutra__[a-z0-9_]+$")


def main():
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        return                      # unreadable: decide nothing, let the mode rule

    name = str(payload.get("tool_name") or "")
    if not ALLOW.match(name):
        # NOT a denial -- staying silent leaves the operator's permission mode
        # in charge. Emitting "deny" here would make this hook an authority on
        # every tool in the session, which is not what it is for.
        return

    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason":
            "Sutra's own tools. Reads are read-only; anything that would change "
            "something writes a proposal the operator must approve in the panel.",
    }}, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
