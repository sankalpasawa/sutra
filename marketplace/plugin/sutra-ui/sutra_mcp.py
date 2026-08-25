#!/usr/bin/env python3
"""sutra_mcp.py — the tool surface the Sutra chat agent gets.

Ask the chat "make me a routine that summarises this repo every weekday at 9"
and it can now DO it, instead of describing one. This is the server that makes
that possible.

WHY MCP, AND WHY STDIO
    MCP is Claude Code's own extension mechanism, so the tools appear to the
    agent exactly like its built-ins and need no side channel. The server is
    spawned BY THE CLI over stdio, for one run, via --mcp-config: it is scoped
    to the process that started it and it never writes to the operator's global
    ~/.claude.json. Nothing is installed; nothing outlives the turn.

    Raw JSON-RPC over stdin/stdout, no SDK: this app ships a bundled CPython
    carrying fastapi, uvicorn and websockets and nothing else. A dependency here
    would have to be vendored into every DMG.

READS ACT. MUTATIONS PROPOSE.
    The read tools answer from the real store. The mutating tools write an inert
    PROPOSAL and return its id immediately -- see proposals.py for why. In
    short: a non-interactive run has nobody to approve anything, so a tool that
    waited would hang the turn; and a sentence in a prompt must not be enough
    authority to install a scheduled job on someone's Mac.

    So the agent never blocks, and nothing changes until the operator clicks
    Approve in the panel.
"""
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import proposals                                        # noqa: E402
import teamsutra                                        # noqa: E402
import routines                                         # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER = {"name": "sutra", "version": "1"}

#: The session this server was spawned for, if the caller told us. Recorded on a
#: proposal so the panel can say which conversation asked for it.
SESSION_ID = os.environ.get("SUTRA_MCP_SESSION") or None


def _text(s):
    return {"content": [{"type": "text", "text": s}]}


def _err(s):
    return {"content": [{"type": "text", "text": s}], "isError": True}


# ------------------------------------------------------------------ reads ---

def t_routines_list(_args):
    st = routines.state()
    if not st["routines"]:
        return _text("There are no routines yet. Propose one with "
                     "sutra_routine_create.")
    lines = []
    for r in st["routines"]:
        if r.get("unreadable"):
            lines.append("- %s — UNREADABLE: %s" % (r["id"], r["unreadable"]))
            continue
        last = r.get("last_run") or {}
        lines.append(
            "- %s — %s | %s | %s | %s%s" % (
                r["id"], r.get("description") or "",
                (r.get("schedule") or {}).get("human") or "?",
                "active" if r.get("enabled") else "paused",
                "never run" if r.get("never_run")
                else "last %s" % (last.get("outcome") or "?"),
                "" if not r.get("never_fired_on_schedule")
                else " (never fired on schedule — only run by hand)"))
    return _text("\n".join(lines))


def t_routine_runs(args):
    rid = str(args.get("id") or "")
    try:
        rr = routines.runs(rid, limit=int(args.get("limit") or 5))
    except (KeyError, OSError) as exc:
        return _err("could not read runs for %r: %s" % (rid, exc))
    if not rr["runs"]:
        return _text("%s has never run." % rid)
    return _text("\n".join(
        "- %s | %s | %s | %ss%s" % (
            r.get("started_at"), r.get("outcome"), r.get("trigger"),
            r.get("duration_s"),
            " | $%.4f" % r["cost_usd"] if r.get("cost_usd") is not None else "")
        for r in rr["runs"]))


def t_org_summary(_args):
    """Counts only. The chat can already read files; what it cannot do is see
    the registry the panel is showing the operator."""
    try:
        import placement_engine as E
        domains = E.load_domains()
        live = E.live_refs(domains)
        return _text("Departments: %d (%d live). Registry: %s"
                     % (len(domains), len(live),
                        os.environ.get("SUTRA_NATIVE_HOME", "?")))
    except Exception as exc:                            # noqa: BLE001
        return _err("could not read the registry: %s" % exc)


def t_proposal_status(args):
    pid = str(args.get("id") or "")
    try:
        p = proposals.get(pid)
    except KeyError:
        return _err("no proposal %r" % pid)
    msg = "%s — %s (%s)" % (p["id"], p["status"], p["summary"])
    if p.get("result"):
        msg += "\nresult: " + json.dumps(p["result"])[:400]
    return _text(msg)


# ------------------------------------------------------------- proposals ---

def _propose(kind, args, summary):
    p = proposals.create(kind, args, summary, session_id=SESSION_ID)
    # The wording matters: the agent must not tell the operator the thing is
    # done. It is not done. It is waiting for them.
    return _text(
        "PROPOSAL %s — awaiting approval in the panel.\n"
        "Nothing has changed yet. The operator sees this under Routines and can "
        "approve or reject it. Tell them what you proposed and why; do not claim "
        "it exists." % p["id"])


def t_routine_create(args):
    """Validated HERE, before anything is proposed. A proposal that cannot
    possibly apply is worse than a refusal: the operator would approve it and
    then watch it fail for a reason they were never shown."""
    body = {
        "id": args.get("id"),
        "description": args.get("description"),
        "prompt": args.get("prompt"),
        "cwd": args.get("cwd"),
        "model": args.get("model") or "",
        "permission_mode": args.get("permission_mode") or routines.DEFAULT_ROUTINE_MODE,
        "opts": {"max_budget_usd": args.get("max_budget_usd", 1.0)},
        "schedule": args.get("schedule") or {"preset": "manual"},
        "enabled": True,
    }
    try:
        routines.validate_new(body, set(routines.list_ids()))
    except ValueError as exc:
        return _err("that routine would be refused: %s" % exc)
    sched = (body["schedule"] or {}).get("preset", "manual")
    return _propose("routine.create", body,
                    "create routine %r (%s)" % (body["id"], sched))


def t_routine_update(args):
    rid = str(args.get("id") or "")
    try:
        routines.load(rid)
    except (KeyError, ValueError) as exc:
        return _err("no routine %r (%s)" % (rid, exc))
    patch = {k: args[k] for k in
             ("description", "prompt", "cwd", "model", "schedule", "enabled")
             if k in args and args[k] is not None}
    if not patch:
        return _err("nothing to change -- name at least one field")
    return _propose("routine.update", {"id": rid, "patch": patch},
                    "update routine %r (%s)" % (rid, ", ".join(sorted(patch))))


def t_routine_delete(args):
    rid = str(args.get("id") or "")
    try:
        routines.load(rid)
    except (KeyError, ValueError) as exc:
        return _err("no routine %r (%s)" % (rid, exc))
    return _propose("routine.delete", {"id": rid}, "delete routine %r" % rid)


def t_routine_run(args):
    rid = str(args.get("id") or "")
    try:
        routines.load(rid)
    except (KeyError, ValueError) as exc:
        return _err("no routine %r (%s)" % (rid, exc))
    # Running spends money on the operator's plan, so it is a proposal too.
    return _propose("routine.run", {"id": rid}, "run routine %r now" % rid)



def t_task_file(args):
    """File a Teamsutra task. DIRECT write, not a proposal — and that is safe
    for exactly one reason: the record lands at status='draft', which nothing
    may claim. Creation is inert; only an operator queues it. Validated here
    so a refusal reaches the agent with the reason."""
    body = {
        "title": str(args.get("title") or ""),
        "body": str(args.get("body") or ""),
        "kind": str(args.get("kind") or "bug"),
        "verify": str(args.get("verify") or ""),
        "source": args.get("source") or {},
    }
    try:
        rec = teamsutra.create(body)
    except ValueError as exc:
        return _err("that task would be refused: %s" % exc)
    return _text(
        "TASK %s filed as a DRAFT.\n"
        "It does nothing until the operator queues it on the Teamsutra screen. "
        "Tell them what you filed and why; do not claim any work has started."
        % rec["id"])


TOOLS = [
    {"name": "sutra_routines_list", "fn": t_routines_list,
     "description": "List the operator's local scheduled routines with their "
                    "schedule, state and last run.",
     "schema": {"type": "object", "properties": {}}},

    {"name": "sutra_routine_runs", "fn": t_routine_runs,
     "description": "Recent runs of one routine: outcome, trigger, duration, cost.",
     "schema": {"type": "object", "required": ["id"], "properties": {
         "id": {"type": "string"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 50}}}},

    {"name": "sutra_org_summary", "fn": t_org_summary,
     "description": "Counts from the placement registry this panel is showing.",
     "schema": {"type": "object", "properties": {}}},

    {"name": "sutra_proposal_status", "fn": t_proposal_status,
     "description": "Whether a proposal you made was approved, rejected or is "
                    "still waiting.",
     "schema": {"type": "object", "required": ["id"], "properties": {
         "id": {"type": "string"}}}},

    {"name": "sutra_routine_create", "fn": t_routine_create,
     "description": "PROPOSE a new scheduled routine. This does NOT create it: "
                    "the operator must approve it in the panel. Schedule presets "
                    "are manual, hourly, daily, weekdays, weekly.",
     "schema": {"type": "object",
                "required": ["id", "description", "prompt", "cwd"],
                "properties": {
                    "id": {"type": "string",
                           "description": "kebab-case, e.g. morning-brief"},
                    "description": {"type": "string"},
                    "prompt": {"type": "string",
                               "description": "what Sutra runs on each fire"},
                    "cwd": {"type": "string",
                            "description": "absolute path inside the home directory"},
                    "model": {"type": "string", "enum": ["", "opus", "sonnet", "haiku"]},
                    "permission_mode": {"type": "string", "enum": ["dontAsk", "plan"]},
                    "max_budget_usd": {"type": "number", "minimum": 0.01},
                    "schedule": {"type": "object", "properties": {
                        "preset": {"type": "string",
                                   "enum": ["manual", "hourly", "daily",
                                            "weekdays", "weekly", "custom"]},
                        "hour": {"type": "integer", "minimum": 0, "maximum": 23},
                        "minute": {"type": "integer", "minimum": 0, "maximum": 59},
                        "weekday": {"type": "integer", "minimum": 0, "maximum": 6},
                        "cron": {"type": "string"}}}}}},

    {"name": "sutra_routine_update", "fn": t_routine_update,
     "description": "PROPOSE a change to a routine, including pausing or "
                    "resuming it. Requires the operator's approval.",
     "schema": {"type": "object", "required": ["id"], "properties": {
         "id": {"type": "string"}, "description": {"type": "string"},
         "prompt": {"type": "string"}, "cwd": {"type": "string"},
         "model": {"type": "string"}, "enabled": {"type": "boolean"},
         "schedule": {"type": "object"}}}},

    {"name": "sutra_routine_delete", "fn": t_routine_delete,
     "description": "PROPOSE deleting a routine. Requires approval.",
     "schema": {"type": "object", "required": ["id"], "properties": {
         "id": {"type": "string"}}}},

    {"name": "sutra_routine_run", "fn": t_routine_run,
     "description": "PROPOSE running a routine now. This spends money on the "
                    "operator's plan, so it requires approval.",
     "schema": {"type": "object", "required": ["id"], "properties": {
         "id": {"type": "string"}}}},

    {"name": "sutra_task_file", "fn": t_task_file,
     "description": "File a Teamsutra task (bug/task/question) as a DRAFT. "
                    "Inert until the operator queues it — never claim work "
                    "has started.",
     "schema": {"type": "object", "required": ["title", "body"], "properties": {
         "title": {"type": "string"}, "body": {"type": "string"},
         "kind": {"type": "string", "enum": ["bug", "task", "question"]},
         "verify": {"type": "string"},
         "source": {"type": "object",
                    "description": "Where the task came from. Pass the "
                                   "selection and screen you were briefed "
                                   "with, and `ask` = the operator's own "
                                   "words, verbatim — the board shows both.",
                    "properties": {
                        "selection": {"type": "string"},
                        "ask": {"type": "string"},
                        "screen": {"type": "string"},
                        "domain_ref": {"type": ["string", "null"]},
                        "domain_path": {"type": ["string", "null"]},
                        "domain_name": {"type": ["string", "null"]},
                        "charter_id": {"type": ["string", "null"]},
                        "session_id": {"type": ["string", "null"]}}}}}},
]
# ---- Shadow tools (PLAN-100 S31+) ------------------------------------------
# Registered ONLY when the shadow flag is true AT SERVER SPAWN. This server is
# spawned per run (--mcp-config), so the flag is re-evaluated every time the
# CLI starts it; with the flag off these names do not exist in tools/list at
# all -- absence, not refusal, is the off-state.
# Registration requires BOTH the flag and the spawn-env marker: the same MCP
# server serves ordinary chat panes, and a chat agent must never see Shadow
# tools -- only Shadow's own session (spawned with SUTRA_MCP_SHADOW=1) does.
# Listing is NOT authorization (dual-lane fold, 2026-08-25): each handler
# re-checks the flag at call time, and a persistent agent process keeps its
# spawn-time tool table until it respawns -- pinned in tests.
try:
    import providers as _providers
    import session_reader as _session_reader
    _SHADOW_ON = (_providers.shadow_enabled()
                  and os.environ.get("SUTRA_MCP_SHADOW") == "1")
except Exception:
    _SHADOW_ON = False

if _SHADOW_ON:
    def t_shadow_sessions_list(args):
        # call-time authorization: hiding a name is not a permission model
        if not _providers.shadow_enabled():
            return _text("refused: the shadow flag is off")
        limit = args.get("limit") or 25
        rows = _session_reader.list_sessions(limit=min(int(limit), 100))
        import time as _time
        now = _time.time()
        out = []
        for r in rows:
            out.append({
                "session_id": r.get("id") or r.get("session_id"),
                "title": r.get("title"),
                "mtime": r.get("mtime"),
                "liveness": _session_reader.liveness(r.get("mtime") or 0, now),
            })
        return _text(json.dumps(out))

    TOOLS.append({
        "name": "shadow_sessions_list", "fn": t_shadow_sessions_list,
        "description": "List Claude Code sessions on this machine with "
                       "liveness (live/recent/idle) so Shadow can decide "
                       "what it is watching.",
        "schema": {"type": "object", "properties": {
            "limit": {"type": "integer", "maximum": 100}}},
    })

BY_NAME = {t["name"]: t for t in TOOLS}


# ----------------------------------------------------------------- server ---

def _send(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def _handle(req):
    m, rid = req.get("method"), req.get("id")
    if m == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER}}
    if m in ("notifications/initialized", "initialized"):
        return None                                   # notification: no reply
    if m == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
            {"name": t["name"], "description": t["description"],
             "inputSchema": t["schema"]} for t in TOOLS]}}
    if m == "tools/call":
        p = req.get("params") or {}
        t = BY_NAME.get(p.get("name"))
        if not t:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": "no tool %r" % p.get("name")}}
        try:
            return {"jsonrpc": "2.0", "id": rid, "result": t["fn"](p.get("arguments") or {})}
        except Exception as exc:                       # noqa: BLE001
            # A tool that raises must not kill the server: the agent gets the
            # failure as a result and can carry on.
            return {"jsonrpc": "2.0", "id": rid,
                    "result": _err("%s failed: %s" % (t["name"], exc))}
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": "unsupported method %r" % m}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        try:
            out = _handle(req)
        except Exception:                              # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            continue
        if out is not None:
            _send(out)


if __name__ == "__main__":
    main()
