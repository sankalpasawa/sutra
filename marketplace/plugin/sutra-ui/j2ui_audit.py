"""j2ui_audit.py -- what Audit read, the conditions the check engine recorded, and the disagreements (UI port, package j2ui-work).

The page's Audit tab shows, for each reading, an 'all pass' or 'failing' heading, a row for each done-when item with PASS or
NEEDS_REVISION, and, above them, 'Workable (checked by code)' once nothing stops the site being workable. Sutra records no
verdict for each item today. What a clean reading leaves is one event in the ledger (audit.finding_filed, severity none: 'Audit
read Live site v2 and found nothing to put right'), and what a reading with findings leaves is Audit's post to Identity. If a
clean event were drawn as the page draws a pass, the tab would say item by item that every item passed, and that code checked
the site was workable, and neither was done. So:

    build_audits(ctx)      one entry for each reading that was read, oldest first. A clean reading has all_pass and a `read`
                           line and no row for any item; a reading with findings has a row for each finding and no row for any
                           item. A reading that was not read (audit.not_read) is no entry: nothing is found and nothing is
                           cleared, and the cycle's own words ('Audit has not read the result') already say so
    build_conditions(ctx)  the check engine's recorded check on the latest version of the previewable artifact, named for what
                           it is (a recorded check, run by code); None when no version has one
    build_workable(ctx)    None: nobody has checked it item by item. The page then draws no 'Workable' line and no pass
    refs(ctx)              api/refs: the conditions' texts by id, and no rubric (Sutra has none)
    audits_condensed(ctx)  api/audits: earlier stages' audits; Sutra keeps no stage before the current one, so none
    build_conflicts(ctx)   the Conflicts tab: a bargain between Adaptation and Priority in which Priority asked for less or said
                           no, and any the two took to Identity. A straight yes is not a conflict. Each attempt says the act in
                           the owner's words, the same words the chat prints for the same post (functions_view._did)

Every builder memoises on ctx.memo and never raises: a failure gives the empty form and a reason on ctx.reasons. Nothing here
writes, speaks or calls a model, and every string the record wrote passes owner_words.
"""
import engine_runtime as R
import functions_view as F
import j2ui_atoms as A
import owner_words

NOTHING = "found nothing to put right"                        # the words of a clean reading, if the record's own are missing


# ---- the readings -----------------------------------------------------------------------------------------------------
def _version(v):
    """A version as the page prints it ('v2'): an int, else '' (never None, which the page would print as 'vnull')."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return ""


def _is_finding(p):
    return p.get("src") == "Audit" and "Identity" in (p.get("dst") or []) and (p.get("payload") or {}).get("word") == "finding"


def _is_clean(e):
    return e.get("action") == "audit.finding_filed" and str((e.get("payload") or {}).get("severity")) == "none"


def _finding_rows(p):
    """A reading's findings as the page's extra issues: F-1 on, each with the page it is on and how serious Audit called it."""
    pl = p.get("payload") or {}
    found = [f for f in pl.get("findings") or [] if isinstance(f, dict) and f.get("claim")]
    if not found and pl.get("claim"):
        found = [{"claim": pl.get("claim"), "severity": pl.get("severity")}]
    return [{"id": "F-%d" % n, "criterion": A.plain(f["claim"]), "verdict": "NEEDS_REVISION", "pass": False,
             "note": A.plain(f.get("page")), "severity": str(f.get("severity") or "low")} for n, f in enumerate(found, 1)]


def _entry(n, version, all_pass, extra, read):
    return {"cycle": n, "version": version, "all_pass": all_pass, "screenshot": None, "results": [], "extra_issues": extra,
            "rubric": [], "conditions": [], "read": read}


def _audits(ctx):
    seen = []
    for p in ctx.posts:
        if _is_finding(p):
            seen.append((A.epoch(p.get("at")) or 0, 0, p.get("n") or 0, "finding", p))
    for e in ctx.events:
        if _is_clean(e):
            seen.append((A.epoch(e.get("occurred_at")) or 0, 1, e.get("seq") or 0, "clean", e))
    out = []
    for n, (_at, _rank, _k, kind, row) in enumerate(sorted(seen, key=lambda x: x[:3]), 1):
        if kind == "finding":
            pl = row.get("payload") or {}
            about = row.get("about") if isinstance(row.get("about"), dict) else {}
            out.append(_entry(n, _version(pl.get("about_version", about.get("v"))), False, _finding_rows(row), ""))
        else:
            ref = next((r for r in row.get("evidence_refs") or [] if isinstance(r, dict) and r.get("version") is not None), {})
            out.append(_entry(n, _version(ref.get("version")), True, [], A.plain(row.get("summary")) or "Audit %s." % NOTHING))
    return out


def build_audits(ctx):
    return A.memoised(ctx, "j2ui_audit.audits", _audits, list, "audits")


# ---- the necessary conditions: the check engine's recorded check ---------------------------------------------------------
def _previewable(ctx):
    """The artifact the page previews: the build, else the last thing the department files."""
    arts = list(getattr(ctx, "arts", None) or [])
    return next((a for a in arts if a.get("name") == "Build"), arts[-1] if arts else None)


def _conditions(ctx):
    art = _previewable(ctx)
    last = ((art or {}).get("versions") or [None])[-1]
    check = (last or {}).get("check")
    if not isinstance(check, dict) or not check:
        return None
    maker = next((e.get("name") for e in ctx.engines if e.get("writes") == art.get("name")), None)
    who = "%s engine" % maker if maker else "Department"
    where = "%s, %s v%s" % (who, art["name"], last.get("v"))
    generic = "The %s passes the %s's check" % (art["name"].lower(), who if maker else "department")
    notes = [A.plain(n) for n in check.get("notes") or [] if A.plain(n)]
    if check.get("ok") is True:
        return [{"id": "N%d" % i, "text": t, "met": True, "evidence": where} for i, t in enumerate(notes or [generic], 1)]
    return [{"id": "N1", "text": generic, "met": False, "evidence": "; ".join(notes) or "its check failed"}]


def build_conditions(ctx):
    return A.memoised(ctx, "j2ui_audit.conditions", _conditions, lambda: None, "conditions")


# ---- what nobody has checked item by item ----------------------------------------------------------------------------------
def build_workable(ctx):
    """None until a reading records a verdict for each done-when item (the page draws 'Workable (checked by code)' for [] and
    'Not workable yet' for a list): a clean reading is not that, so the tab draws neither."""
    return None


def refs(ctx):
    """api/refs: the text of each condition by its id; Sutra has no rubric."""
    return {"conditions": {c["id"]: c["text"] for c in build_conditions(ctx) or []}, "rubric": {}}


def audits_condensed(ctx):
    """api/audits: earlier stages' audits, condensed. Sutra keeps one live cycle and no stage before it."""
    return []


# ---- the conflicts: Adaptation and Priority disagreeing -------------------------------------------------------------------
BARGAIN_ACTS = ("propose", "accept-proposal", "reject-proposal")
ATTEMPTS = R.BOUNDS["hops"]                                    # the bound a bargain has before it goes to Identity


def _bargain(p):
    """A post of the bargain over the line: Adaptation proposes, Priority says yes, asks for less or says no."""
    return (p.get("src") in ("Adaptation", "Priority") and p.get("msg_type") in BARGAIN_ACTS
            and (p.get("payload") or {}).get("word") == "line")


def _act(p):
    """A post as the act its function did, in the owner's words, then what it carried: 'Said yes to the plan: it fits today'.
    The one line the chat prints for a function's post (functions_view._did and _said), so the tab and the chat agree."""
    did = F._did(p)
    said = F._short(F._said(p))
    return (did[:1].upper() + did[1:]) + (": %s" % said if said else "")


def _position(p, first):
    """(position, agrees) of one attempt. Adaptation's later proposals take Priority's ask for less, so they agree."""
    act = p.get("msg_type")
    if p.get("src") == "Adaptation":
        return ("opening proposal", None) if first else ("said yes", True)
    return {"accept-proposal": ("said yes", True), "propose": ("asked for less", False)}.get(act, ("said no", False))


def _names(p):
    return [{"name": str(e.get("name")), "cost": None} for e in (p.get("payload") or {}).get("engines") or [] if isinstance(e, dict)
            and e.get("name")]


def _finals(posts):
    """What each side stood on at the end: Adaptation's last proposal, and what Priority would have run (all of it after a yes,
    what it kept after asking for less, nothing after a no). No cost is recorded for a proposed workflow, so none is said."""
    mine = [p for p in posts if p.get("src") == "Adaptation"]
    theirs = [p for p in posts if p.get("src") == "Priority"]
    proposed = _names(mine[-1]) if mine else []
    if not theirs:
        return proposed, []
    last = theirs[-1]
    if last.get("msg_type") == "accept-proposal":
        return proposed, proposed
    if last.get("msg_type") == "propose":
        return proposed, [{"name": str(n), "cost": None} for n in (last.get("payload") or {}).get("keep") or []]
    return proposed, []


def _ledger(ctx, thread):
    """What the ledger says of this bargain: Identity's ruling (the one after the conflict was raised) and the workflow
    registered once it was settled. Both None when the cycle's ledger does not hold the thread."""
    events = sorted(ctx.events, key=lambda e: e.get("seq") or 0)
    mine = [e for e in events if e.get("proposal_ref") == thread]
    raised = next((e for e in mine if e.get("action") == "conflict.raised"), None)
    anchor = raised or (mine[-1] if mine else None)
    if anchor is None:
        return None, None
    after = [e for e in events if (e.get("seq") or 0) > (anchor.get("seq") or 0)]
    ruled = None
    registered = None
    for e in after if raised else []:                            # a ruling answers a conflict that was raised, and nothing else
        if e.get("action") == "conflict.raised":
            break
        if e.get("action") == "identity.ruled":
            ruled = e
            break
    for e in after:
        if e.get("action") == "proposal.created" and e.get("proposal_ref") not in (None, thread):
            break
        if e.get("action") == "workflow.registered":
            registered = [str(n) for n in (e.get("payload") or {}).get("workflow") or []]
            break
    return ruled, registered


def _outcome(resolved_by, agreed_after, ruling, ask, last, escalated):
    if resolved_by == "agents":
        return "Settled between the two: Priority said yes%s." % (" after asking for less" if agreed_after else "")
    if resolved_by == "identity":
        return "Identity ruled it runs." if ruling == "run" else "Identity dropped the plan."
    if resolved_by == "identity_after_user":
        return "You stamped the plan as proposed." if (ask or {}).get("status") == "stamped" else "You said no, so the plan is dropped."
    if ask and ask.get("status") == "pending":
        return "Waiting for your answer."
    if escalated:
        return "Waiting for Identity."
    if last is not None and last.get("src") == "Priority" and last.get("msg_type") == "propose":
        return "Waiting for Adaptation to answer Priority's ask for less."
    return "Waiting for Identity." if last is not None and last.get("msg_type") == "reject-proposal" else ""


def _conflict(ctx, n, thread, posts, conflicts):
    msgs = getattr(ctx, "msg_of", None) or {}
    attempts = []
    for i, p in enumerate(posts):
        position, agree = _position(p, i == 0)
        text = _act(p)
        attempts.append({"n": i, "who": p["src"].lower(), "msg": msgs.get(("b", p.get("n"))), "text": text, "position": position, "agree": agree})
    used = len([a for a in attempts if a["n"] > 0])
    last = posts[-1] if posts else None
    ruled, registered = _ledger(ctx, thread)
    ruling = str((ruled or {}).get("state") or ((ruled or {}).get("payload") or {}).get("ruling") or "")
    ask = next((a for a in ctx.asks if a.get("kind") == "conflict" and a.get("for") == thread), None)
    answered = (ask or {}).get("status") in ("stamped", "refused")
    escalated = bool(conflicts) or bool(ruled) or bool(ask)
    agreed = last is not None and last.get("src") == "Priority" and last.get("msg_type") == "accept-proposal" and not escalated
    resolved_by = "agents" if agreed else "identity_after_user" if answered else "identity" if ruling in ("run", "drop") else None
    identity = []
    if ruled:
        identity.append({"after_user": False, "resolved": ruling in ("run", "drop"), "ruling": F.RULING_SAYS.get(ruling, ruling), "clause": "",
                         "say": A.plain(ruled.get("summary"))})
    if answered:
        stamped = ask["status"] == "stamped"
        identity.append({"after_user": True, "resolved": True, "ruling": F.RULING_SAYS["run" if stamped else "drop"], "clause": "",
                         "say": "You stamped the plan as proposed." if stamped else "You said no to the plan."})
    mine, theirs = _finals(posts)
    first = (posts[0].get("payload") or {}) if posts else {}
    return {"id": "C-%d" % n, "cycle": (ctx.cur or {}).get("round") or 1, "topic": "proposal", "between": ["adaptation", "priority"],
            "about": None, "subject": A.plain(first.get("why")) or "what to run", "detail": None, "attempts": attempts,
            "status": "settled" if resolved_by else "open", "escalated": escalated,
            "attempts_before_escalation": min(ATTEMPTS, used) if escalated else 0, "resolved_by": resolved_by, "identity": identity,
            "escalated_to_user": bool(ask) or ruling == "ask",
            "user_question": {"question": owner_words.kept(ask.get("text"), ask.get("words")), "options": ["Stamp", "Say no"]} if ask else None,
            "user_answer": ("Stamp" if ask["status"] == "stamped" else "Say no") if answered else None, "winner": None,
            "outcome": _outcome(resolved_by, any(p.get("msg_type") == "propose" and p.get("src") == "Priority" for p in posts), ruling, ask, last,
                                escalated),
            "priority_final": theirs, "adaptation_final": mine, "attempts_used": used, "registered": registered}


def _conflicts(ctx):
    by = {}
    for p in ctx.posts:
        if _bargain(p):
            by.setdefault(p.get("thread"), []).append(p)
    raised = {}
    for p in ctx.posts:
        pl = p.get("payload") or {}
        if pl.get("word") == "conflict" and "Identity" in (p.get("dst") or []) and pl.get("for"):
            raised.setdefault(pl["for"], []).append(p)
    disagreed = [t for t, ps in by.items() if any(p["src"] == "Priority" and p["msg_type"] != "accept-proposal" for p in ps)]
    threads = sorted(set(disagreed) | set(raised), key=lambda t: min([p.get("n") or 0 for p in by.get(t, []) + raised.get(t, [])]))
    return [_conflict(ctx, n, t, sorted(by.get(t, []), key=lambda p: p.get("n") or 0), raised.get(t, [])) for n, t in enumerate(threads, 1)]


def build_conflicts(ctx):
    return A.memoised(ctx, "j2ui_audit.conflicts", _conflicts, list, "conflicts")
