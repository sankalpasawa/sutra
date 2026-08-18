#!/usr/bin/env python3
"""Balance daily coach pass (plugin port, PLAN-25 step 20) — fold ledger, evaluate predicates, emit events.

Consult folds (2026-08-18, codex + deepseek convergent):
- 'surfaced' is DERIVED (days_open), never emitted.
- Event emission dedups against folded state; daily-pass rows keyed by date.
- Derived actionables.json written tempfile+rename; folds tolerate bad lines.
- Predicates: file-exists / grep-count (fixed-string, root-resolved, 1MB cap)
  / builtin (code-implemented). No shell execution from ledger rows.
"""
import json, os, sys, time, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
# Testability override (consult fold: validated absolute path or ignored —
# arbitrary inherited env must not silently redirect production state).
_ENV_BAL = os.environ.get("SUTRA_BALANCE_STATE_DIR", "")
_PROJ = os.environ.get("CLAUDE_PROJECT_DIR", "")
_CANDIDATES = [_ENV_BAL,
               os.path.join(_PROJ, ".sutra", "balance") if _PROJ else "",
               os.path.join(REPO, "holding", "state", "balance")]
BAL = next(c for c in _CANDIDATES if c and os.path.isabs(c) and os.path.isdir(c))
LEDGER = os.path.join(BAL, "coach-ledger.jsonl")
DERIVED = os.path.join(BAL, "actionables.json")
INSIGHTS = os.path.join(BAL, "insights.jsonl")
BLOG = os.path.join(BAL, "balance-log.jsonl")
NOW = int(time.time())
TODAY = time.strftime("%Y-%m-%d", time.localtime(NOW))


def rows(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue  # partial/corrupt trailing line: skip, never crash
    except OSError:
        return


def repo_path(rel):
    """Root-resolved + containment-checked path, or None."""
    p = os.path.realpath(os.path.join(REPO, rel))
    return p if p.startswith(REPO + os.sep) else None


def pred_file_exists(args):
    p = repo_path(args[0])
    return bool(p and os.path.exists(p))


def pred_grep_count(args):
    needle, rel, op, n = args[0], args[1], args[2], int(args[3])
    p = repo_path(rel)
    if not p or not os.path.isfile(p) or os.path.getsize(p) > 1_000_000:
        return False
    count = 0
    with open(p, encoding="utf-8", errors="replace") as f:
        for line in f:
            count += line.count(needle)  # fixed-string, never regex
    return {"<": count < n, "<=": count <= n, "==": count == n,
            ">=": count >= n, ">": count > n}.get(op, False)


def builtin_late_night_clear(days=14):
    cutoff = NOW - days * 86400
    for r in rows(BLOG):
        ep = r.get("epoch")
        if not isinstance(ep, (int, float)) or ep < cutoff:
            continue
        h = time.localtime(ep).tm_hour
        if 1 <= h < 5:
            return False
    return True


def builtin_audit_critical_clear():
    last = {}
    for r in rows(os.path.join(REPO, "holding", "observability", "governance-audit", "findings.jsonl")):
        if r.get("id"):
            last[r["id"]] = r
    return not any(v.get("severity") == "critical" and v.get("status") == "open"
                   for v in last.values())


BUILTINS = {"late-night-clear-14": lambda: builtin_late_night_clear(14),
            "audit-critical-clear": builtin_audit_critical_clear}

# Evidence doctrine (EVIDENCE.md, dual-lane consult folds 2026-08-18):
# instrument-owned sources only; every coach-written file is denied outright —
# a witness may not attest to its own testimony. Guard targets naive
# self-attestation, not a full trust boundary (documented limitation).
SOURCE_ALLOW_DIRS = ("holding/observability/",)
SOURCE_ALLOW_FILES = ("holding/state/balance/balance-log.jsonl",)
SOURCE_DENY_FILES = ("holding/state/balance/actionables.json",
                     "holding/state/balance/insights.jsonl",
                     "holding/state/balance/coach-ledger.jsonl",
                     "holding/state/balance/roles-dashboard.html")


def validate_predicate(pred, at_birth=False):
    """EVIDENCE.md rules 1-3 (every fold) + rule 4 (birth only, builtins
    exempt). Returns (valid, reason). Invalid = founder-word-only closing."""
    if not isinstance(pred, dict):
        return False, "not-a-dict"
    t, a = pred.get("template"), pred.get("args", [])
    if t == "builtin":
        return (True, "") if a and a[0] in BUILTINS else (False, "unknown-builtin")
    if t == "file-exists":
        rel = a[0] if a else ""
    elif t == "grep-count":
        rel = a[1] if len(a) > 1 else ""
    else:
        return False, "unknown-template"
    if repo_path(rel) is None:
        return False, "outside-repo"
    norm = rel.lstrip("./")
    if norm in SOURCE_DENY_FILES:
        return False, "self-attesting-source"
    if not (norm in SOURCE_ALLOW_FILES or any(norm.startswith(d) for d in SOURCE_ALLOW_DIRS)):
        return False, "source-not-instrument-owned"
    if at_birth and evaluate(pred):
        return False, "already-true-at-birth"
    return True, ""


def evaluate(pred):
    try:
        t, a = pred.get("template"), pred.get("args", [])
        if t == "file-exists":
            return pred_file_exists(a)
        if t == "grep-count":
            return pred_grep_count(a)
        if t == "builtin" and a and a[0] in BUILTINS:
            return BUILTINS[a[0]]()
    except Exception:
        return False  # a broken predicate is a failed predicate, never a crash
    return False


def main():
    events = list(rows(LEDGER))
    acts = {}
    daily_done_today = False
    for e in events:
        ev, aid = e.get("event"), e.get("id")
        if ev == "daily-pass" and e.get("date") == TODAY:
            daily_done_today = True
        if not aid:
            continue
        if ev == "born":
            acts[aid] = dict(e, status="open", movements=0)
        elif aid in acts and ev == "movement":
            acts[aid]["movements"] += 1
            acts[aid]["last_movement"] = e.get("ts")
        elif aid in acts and ev in ("done", "dropped"):
            acts[aid]["status"] = ev
            acts[aid]["closed_ts"] = e.get("ts")
            acts[aid]["closed_by"] = e.get("by", "founder")

    for a in acts.values():
        if a.get("predicate"):
            ok, why = validate_predicate(a["predicate"])
            a["predicate_valid"] = ok
            if not ok:
                a["predicate_invalid_reason"] = why

    new_events = []
    for aid, a in acts.items():
        if a["status"] != "open" or not a.get("predicate") or not a.get("predicate_valid"):
            continue
        if evaluate(a["predicate"]):
            a["status"] = "done"
            a["closed_ts"] = NOW
            a["closed_by"] = "predicate"
            new_events.append({"ts": NOW, "event": "done", "id": aid, "by": "predicate",
                               "evidence": a["predicate"]})

    if not daily_done_today:
        new_events.append({"ts": NOW, "event": "daily-pass", "date": TODAY, "id": None})
        n_today = sum(1 for r in rows(BLOG)
                      if time.strftime("%Y-%m-%d", time.localtime(r.get("epoch", 0))) == TODAY)
        with open(INSIGHTS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": NOW, "date": TODAY, "kind": "day",
                                "text": f"{n_today} observation windows today; "
                                        f"{sum(1 for a in acts.values() if a['status']=='open')} actionables open."}) + "\n")

    # Weekly rollup: own ISO-week idempotency key, independent of the daily
    # key (consult fold — never nested under daily_done_today).
    iso_week = time.strftime("%G-W%V", time.localtime(NOW))
    weekly_due = ("--weekly" in sys.argv) or time.localtime(NOW).tm_wday == 6
    week_done = any(e.get("event") == "weekly-pass" and e.get("week") == iso_week
                    for e in events)
    if weekly_due and not week_done:
        wk_start = NOW - 7 * 86400
        opened = sum(1 for e in events if e.get("event") == "born" and e.get("ts", 0) >= wk_start)
        closed = sum(1 for e in events if e.get("event") in ("done", "dropped") and e.get("ts", 0) >= wk_start)
        moved = sum(1 for e in events if e.get("event") == "movement" and e.get("ts", 0) >= wk_start)
        late_days = len({time.strftime("%Y-%m-%d", time.localtime(r["epoch"]))
                         for r in rows(BLOG)
                         if isinstance(r.get("epoch"), (int, float)) and r["epoch"] >= wk_start
                         and 1 <= time.localtime(r["epoch"]).tm_hour < 5})
        new_events.append({"ts": NOW, "event": "weekly-pass", "week": iso_week, "id": None})
        with open(INSIGHTS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": NOW, "date": TODAY, "kind": "week", "week": iso_week,
                                "text": f"Week {iso_week}: {opened} actionables opened, {closed} closed, "
                                        f"{moved} progress notes; late-night activity on {late_days} of 7 days."}) + "\n")

    if new_events:
        with open(LEDGER, "a", encoding="utf-8") as f:
            for e in new_events:
                f.write(json.dumps(e) + "\n")

    # Profile read ONCE (consult fold) — used by escalation AND active cap.
    try:
        with open(os.path.join(BAL, "coach-profile.json"), encoding="utf-8") as f:
            profile = json.load(f)
    except (OSError, ValueError):
        profile = {}
    esc_days = int((profile.get("thresholds") or {}).get("recurring_escalate_days", 7))

    for a in acts.values():
        a["days_open"] = max(0, int((NOW - a.get("ts", NOW)) / 86400))
        a["times_surfaced"] = a["days_open"] if a["status"] == "open" else None
        # Escalation (consult fold): movement resets the STALL clock only;
        # total age still escalates at 3x threshold — closing beats note-taking.
        anchor = max(a.get("ts", NOW), a.get("last_movement") or 0)
        a["stalled_days"] = max(0, int((NOW - anchor) / 86400))
        a["escalated"] = (a["status"] == "open"
                          and (a["stalled_days"] >= esc_days
                               or a["days_open"] >= 3 * esc_days))
        a.pop("event", None)
    max_active = int(profile.get("max_active", 3))
    warnings = []
    prio, seen = [], set()
    for i in profile.get("priority", []):
        if i in seen:
            continue
        seen.add(i)
        if i in acts and acts[i]["status"] == "open":
            prio.append(i)
        else:
            warnings.append(f"priority id ignored (closed or unknown): {i}")
    open_ids = prio + [a["id"] for a in sorted(acts.values(), key=lambda a: a.get("ts", 0))
                       if a["status"] == "open" and a["id"] not in seen]
    for n, aid in enumerate(open_ids):
        acts[aid]["active"] = n < max_active

    fd, tmp = tempfile.mkstemp(dir=BAL)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW)),
                   "max_active": max_active, "profile_warnings": warnings,
                   "actionables": sorted(acts.values(), key=lambda a: a.get("ts", 0))}, f, indent=1)
    os.replace(tmp, DERIVED)

    # Slack digest (PLAN-25 step 17): config-gated. Posts only when
    # profile.slack_channel is set AND the connector token exists. As of
    # 2026-08-18 the bot is in zero channels — invite it, then set
    # slack_channel in coach-profile.json to activate. Never crashes the pass.
    chan = profile.get("slack_channel")
    if chan:
        try:
            import urllib.request
            stok = json.load(open(os.path.expanduser(
                "~/.sutra-connectors/oauth/slack.json"))).get("token")
            if stok:
                n_open = sum(1 for a in acts.values() if a["status"] == "open")
                n_act = sum(1 for a in acts.values() if a.get("active"))
                esc_n = sum(1 for a in acts.values() if a.get("escalated"))
                msg = (f"Balance daily ({TODAY}): {n_act} active / {n_open} open actionables"
                       + (f", {esc_n} recurring" if esc_n else "")
                       + f", {len(new_events)} events tonight.")
                req = urllib.request.Request(
                    "https://slack.com/api/chat.postMessage",
                    data=json.dumps({"channel": chan, "text": msg}).encode(),
                    headers={"Authorization": "Bearer " + stok,
                             "Content-Type": "application/json"})
                r = json.loads(urllib.request.urlopen(req, timeout=20).read())
                if not r.get("ok"):
                    print(f"slack digest failed: {r.get('error')}")
        except Exception as e:
            print(f"slack digest error: {e}")
    print(f"coach-pass: {len(acts)} actionables "
          f"({sum(1 for a in acts.values() if a['status']=='open')} open), "
          f"{len(new_events)} new events")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--validate-birth":
        _ok, _why = validate_predicate(json.loads(sys.argv[2]), at_birth=True)
        print(json.dumps({"valid": _ok, "reason": _why}))
        sys.exit(0 if _ok else 1)
    main()
