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

Every builder memoises on ctx.memo and never raises: a failure gives the empty form and a reason on ctx.reasons. Nothing here
writes, speaks or calls a model, and every string the record wrote passes owner_words.
"""
import j2ui_atoms as A

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
