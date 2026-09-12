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



def t_app_check(args):
    """Apps frameworks (design v1 R1-P9): the read-only lane for a chat that is
    building or editing an app when its permission mode refuses a bare Bash
    run. Same runner, same kit, same verdict as `python3 check.py`; this tool
    WRITES the ## Checks block like the CLI does (an explicit run, not a page
    load). Confined to the modules home by realpath."""
    import os as _os
    home = _os.path.realpath(_os.path.expanduser(_os.environ.get("SUTRA_MODULES_HOME", "~/.sutra-ui/modules")))
    mid, path = str(args.get("id") or ""), str(args.get("path") or "")
    folder = _os.path.realpath(_os.path.join(home, mid)) if mid else _os.path.realpath(_os.path.expanduser(path))
    if not folder.startswith(home + _os.sep):
        return _err("that folder is not an app under %s" % home)
    kit_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "apps-frameworks")
    if kit_dir not in sys.path:
        sys.path.insert(0, kit_dir)
    try:
        import check as kit_check
    except Exception as exc:                            # noqa: BLE001
        return _err("the checks runner is not installed: %s" % exc)
    kind = args.get("kind") or None
    results, summary, code = kit_check.run(folder, kind, home=home, kitdir=kit_dir, allow_skip_render=True)
    if code == 2:
        return _err(summary.get("error") or "could not read the app")
    kit_check.write_checks_block(folder, results, summary, {})
    return _text(kit_check.render_table(results, summary) + "\n\nexit %d%s" % (code, "" if code == 0 else " (must-fix results remain)" if code == 1 else " (render not run)"))


def t_app_publish(args):
    """Publish program P3 (ruling P-6): PROPOSE publishing one app. Validated
    here so a proposal that cannot apply is never offered: the app exists under
    the apps home, is ready, and its must-fix checks pass. Approval in the panel
    runs modules_api.publish_app (export, version, signature, staged files)."""
    import os as _os
    home = _os.path.realpath(_os.path.expanduser(_os.environ.get("SUTRA_MODULES_HOME", "~/.sutra-ui/modules")))
    mid = str(args.get("id") or "")
    bump = str(args.get("bump") or "patch")
    if bump not in ("patch", "minor", "major"):
        return _err("bump must be patch, minor or major")
    folder = _os.path.realpath(_os.path.join(home, mid)) if mid else ""
    if not mid or not folder.startswith(home + _os.sep) or not _os.path.isfile(_os.path.join(folder, "module.json")):
        return _err("no app named %r under %s" % (mid, home))
    try:
        raw = json.load(open(_os.path.join(folder, "module.json"), encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _err("the app's manifest does not read: %s" % exc)
    if raw.get("status") != "ready":
        return _err("publish needs a ready app; %r is %s. Ask the operator to mark it ready in the app header once the checks pass." % (mid, raw.get("status") or "unknown"))
    if raw.get("schema") != 2:
        return _err("this app is still manifest schema %r; one edit bumps it to 2 (the write-back), then propose again" % (raw.get("schema"),))
    # what the approval would refuse anyway is refused here, so no proposal is offered that cannot apply (codex item 3)
    import providers as _providers
    flags = _providers._raw_settings().get("flags")
    if not (isinstance(flags, dict) and flags.get("apps_publish") is True):
        return _err("publishing is off: the operator sets flags.apps_publish to true in ~/.sutra-ui/settings.json first")
    import modules_sign as _sign
    if not _sign.available():
        return _err("this desktop cannot sign (the cryptography library is missing); publishing needs it")
    kit_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "apps-frameworks")
    if kit_dir not in sys.path:
        sys.path.insert(0, kit_dir)
    try:
        import check as kit_check
        results, summary, code = kit_check.run(folder, raw.get("kind"), home=home, kitdir=kit_dir, allow_skip_render=True)
        fails = [r["id"] for r in results if r["status"] == "fail" and r["level"] == "must-fix"]
        if fails:
            return _err("the checks block publishing: %s. Fix or waive them, then propose again." % ", ".join(fails))
    except Exception as exc:                            # noqa: BLE001 -- the approval re-checks; here it only advises
        return _err("the checks could not run: %s" % exc)
    cur = ((raw.get("publish") or {}).get("version") if isinstance(raw.get("publish"), dict) else None) or "none yet"
    return _propose("app.publish", {"id": mid, "bump": bump},
                    "publish app %r (%s bump; current version %s)" % (mid, bump, cur))


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

    {"name": "sutra_app_check", "fn": t_app_check,
     "description": "Run the app checks on one app folder under the apps home "
                    "(the same runner as python3 check.py). Read the folder, "
                    "report must-fix results and suggestions, and write the "
                    "## Checks block of its APP.md. Pass id (folder name) or path.",
     "schema": {"type": "object", "properties": {
         "id": {"type": "string", "description": "the app folder name under the apps home"},
         "path": {"type": "string", "description": "absolute path of the app folder (alternative to id)"},
         "kind": {"type": "string", "enum": ["page", "chat", "link"]}}}},

    {"name": "sutra_app_publish", "fn": t_app_publish,
     "description": "PROPOSE publishing one app to the Sutra Apps registry. This "
                    "does NOT publish: the operator approves it in the panel, and "
                    "the approval exports the app, assigns its version, signs the "
                    "registry entry and stages the files under ~/.sutra-ui/publish/. "
                    "The app must be ready with every must-fix check passing.",
     "schema": {"type": "object", "required": ["id"], "properties": {
         "id": {"type": "string", "description": "the app folder name under the apps home"},
         "bump": {"type": "string", "enum": ["patch", "minor", "major"],
                  "description": "how the published version moves (first publish is 1.0.0)"}}}},

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

    import shadow_egress as _shadow_egress
    import shadow_ledger as _shadow_ledger
    import urllib.request as _urlreq
    import urllib.error as _urlerr

    def _shadow_gate():
        """Call-time authorization shared by every shadow tool."""
        if not _providers.shadow_enabled():
            return _text("refused: the shadow flag is off")
        return None

    def t_shadow_session_read_tail(args):
        refused = _shadow_gate()
        if refused:
            return refused
        sid = args.get("session_id") or ""
        limit = min(int(args.get("limit") or 20), 100)
        doc = _session_reader.read_session(sid)
        if not doc:
            return _text("no such session: %s" % sid)
        items = (doc.get("messages") or doc.get("items") or [])[-limit:]
        out = []
        for it in items:
            if isinstance(it, dict):
                txt = str(it.get("text") or it.get("content") or "")[:800]
                out.append({"role": it.get("role") or it.get("type"),
                            "text": txt})
        return _text(json.dumps(out))

    def t_shadow_app_state(args):
        refused = _shadow_gate()
        if refused:
            return refused
        import time as _time
        rows = _session_reader.list_sessions(limit=100)
        now = _time.time()
        live = sum(1 for r in rows
                   if _session_reader.liveness(r.get("mtime") or 0, now) == "live")
        detail = _providers.active_provider_detail()
        # Bounded + redacted by construction: counts and enum-ish fields only.
        # No tokens, no keys, no file contents, no env -- pinned by test.
        return _text(json.dumps({
            "sessions_total": len(rows),
            "sessions_live": live,
            "provider": detail.get("id"),
            "permission_mode": _providers.effective_permission_mode(
                _providers.load_settings()["permission_mode"]),
            "app_version": os.environ.get("SUTRA_UI_VERSION", "unknown"),
        }))

    def t_shadow_ledger_read(args):
        refused = _shadow_gate()
        if refused:
            return refused
        try:
            rows = _shadow_ledger.read(args.get("kind") or "",
                                       args.get("limit") or 50)
        except ValueError as exc:
            return _text(str(exc))
        return _text(json.dumps(rows))

    def t_shadow_ledger_append(args):
        refused = _shadow_gate()
        if refused:
            return refused
        try:
            row = _shadow_ledger.append(args.get("kind") or "",
                                        args.get("row"))
        except ValueError as exc:
            return _text(str(exc))
        return _text(json.dumps(row))

    def t_shadow_session_say(args):
        refused = _shadow_gate()
        if refused:
            return refused
        sid = args.get("session_id") or ""
        port = os.environ.get("SUTRA_UI_PORT", "8330")
        payload = json.dumps({
            "message": args.get("message") or "",
            "mission_id": args.get("mission_id"),
            "dedupe_key": args.get("dedupe_key"),
        }).encode("utf-8")
        req = _urlreq.Request(
            "http://127.0.0.1:%s/api/sessions/%s/say" % (port, sid),
            data=payload, headers={
                "content-type": "application/json",
                # capability, not attribution: minted by the app per boot,
                # inherited via the spawn env; without it the app answers 401
                "x-shadow-say-token":
                    os.environ.get("SUTRA_SHADOW_SAY_TOKEN", ""),
            })
        try:
            with _urlreq.urlopen(req, timeout=10) as resp:
                return _text(resp.read().decode("utf-8", "replace"))
        except _urlerr.HTTPError as exc:
            return _text("refused (%s): %s" % (
                exc.code, exc.read().decode("utf-8", "replace")[:300]))
        except Exception as exc:
            return _text("say failed: %s" % exc)

    def t_shadow_verify(args):
        refused = _shadow_gate()
        if refused:
            return refused
        mode = args.get("mode") or "contains"
        if mode == "contains":
            sid = args.get("session_id") or ""
            needle = args.get("needle") or ""
            doc = _session_reader.read_session(sid)
            hay = json.dumps(doc or {})
            return _text(json.dumps({"mode": mode, "passed": needle in hay}))
        if mode == "ledger_has":
            import shadow_ledger as _sl
            rows = _sl.read(args.get("kind") or "actions", 200)
            needle = args.get("needle") or ""
            return _text(json.dumps({
                "mode": mode,
                "passed": any(needle in json.dumps(r) for r in rows)}))
        if mode == "state":
            # runtime state lives in the APP process; answered over HTTP in a
            # later step -- refuse honestly rather than guessing
            return _text(json.dumps({"mode": mode, "passed": None,
                                     "note": "state assertions land with the "
                                             "mission loop (P3)"}))
        return _text("unknown verify mode %r" % mode)

    def t_shadow_mission_update(args):
        refused = _shadow_gate()
        if refused:
            return refused
        import shadow_ledger as _sl
        states = ("draft", "brief_confirm", "running", "queued", "paused",
                  "done", "failed", "stopped")
        mid = args.get("mission_id") or ""
        state = args.get("state") or ""
        if not mid or state not in states:
            return _text("refused: mission_id and a known state are required")
        row = _sl.append("missions", {
            "mission_id": mid, "state": state,
            "note": str(args.get("note") or "")[:500]})
        return _text(json.dumps(row))

    for _name, _fn, _desc, _schema in [
        ("shadow_session_read_tail", t_shadow_session_read_tail,
         "Last N items of one session transcript, bounded and truncated.",
         {"type": "object", "properties": {
             "session_id": {"type": "string"},
             "limit": {"type": "integer", "maximum": 100}},
          "required": ["session_id"]}),
        ("shadow_app_state", t_shadow_app_state,
         "Bounded, redacted app snapshot: session counts, provider, "
         "permission mode, version.",
         {"type": "object", "properties": {}}),
        ("shadow_ledger_read", t_shadow_ledger_read,
         "Read Shadow ledger rows (instructions|missions|actions).",
         {"type": "object", "properties": {
             "kind": {"type": "string"},
             "limit": {"type": "integer"}}, "required": ["kind"]}),
        ("shadow_ledger_append", t_shadow_ledger_append,
         "Append one row to a Shadow ledger (append-only, inert memory).",
         {"type": "object", "properties": {
             "kind": {"type": "string"}, "row": {"type": "object"}},
          "required": ["kind", "row"]}),
        ("shadow_verify", t_shadow_verify,
         "Assert an outcome: contains (session transcript), ledger_has, "
         "or state (P3).",
         {"type": "object", "properties": {
             "mode": {"type": "string"},
             "session_id": {"type": "string"},
             "kind": {"type": "string"},
             "needle": {"type": "string"}}}),
        ("shadow_mission_update", t_shadow_mission_update,
         "Append a mission state transition to the missions ledger.",
         {"type": "object", "properties": {
             "mission_id": {"type": "string"},
             "state": {"type": "string"},
             "note": {"type": "string"}},
          "required": ["mission_id", "state"]}),
        ("shadow_session_say", t_shadow_session_say,
         "Send one gated, scrubbed, mission-tagged turn into a live session "
         "via the app (delivered only at a turn boundary).",
         {"type": "object", "properties": {
             "session_id": {"type": "string"},
             "message": {"type": "string"},
             "mission_id": {"type": "string"},
             "dedupe_key": {"type": "string"}},
          "required": ["session_id", "message", "mission_id"]}),
    ]:
        TOOLS.append({"name": _name, "fn": _fn, "description": _desc,
                      "schema": _schema})

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
