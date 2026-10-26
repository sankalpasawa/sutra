"""test_j2ui_audit.py -- what Audit read, the recorded conditions, and the disagreements (j2ui_audit.py; UI port, package j2ui-work).

Named claims:
  W5  the Audit tab is honest. A clean reading is one entry with a `read` line and no row for any item, because Sutra records no
      verdict for each item: the tab draws no 'Workable (checked by code)' and no PASS cell for a check nobody made. A reading
      with findings has a row for each finding. A reading that was not read is no entry. The conditions are the check engine's
      recorded check on the build, named for what they are, and none when no version has one. No version is ever null.

The helpers (the stand-in Ctx, the record's writers, the prototype's page rendered in node) are test_j2ui_work.py's.
"""
import json
import re

import pytest

import j2ui_audit as X
import j2ui_work as K
from test_j2ui_work import (BANNED, CHECK_ID, LINE, REF, ago, born, cycle, event, mods, page_state, post, render, run, shown,  # noqa: F401
                            standin, step_row, walk)


def finding(W, R, claims, about_version=2, at=None, **more):
    """Audit's post to Identity, as engine_runtime.audit_file writes it, and the ledger's event beside it."""
    found = [{"page": p, "claim": c, "severity": s} for p, c, s in claims]
    high = [f for f in found if f["severity"] == "high"]
    return post(W, R, "Audit", "Identity", "inform", dict({"word": "finding", "claim": (high or found)[0]["claim"],
                                                           "severity": "high" if high else "low", "findings": found,
                                                           "about_version": about_version}, **more),
                thread="x-find%d" % about_version, about={"art": "Live site", "v": about_version}, at=at)


def build_version(W, check, art="Build", files=None):
    return W.VERS.add(W._abase(REF, art), files or {"index.html": "<p>x</p>"}, [], "r-x", check, W.now())


def audit_of(mods, **kw):
    ctx = standin(mods, **kw)
    return K.build(ctx), ctx


# ---- W5: audits ---------------------------------------------------------------------------------------------------------
def test_w5_a_clean_reading_is_one_entry_with_a_read_line_and_no_item_rows(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    assert J.audited(REF, 2, []) is True
    got, ctx = audit_of(mods)
    assert len(got["audits"]) == 1
    a = got["audits"][0]
    assert list(a) == ["cycle", "version", "all_pass", "screenshot", "results", "extra_issues", "rubric", "conditions", "read"]
    assert (a["cycle"], a["version"], a["all_pass"], a["screenshot"]) == (1, 2, True, None)
    assert a["results"] == [] and a["extra_issues"] == [] and a["rubric"] == [] and a["conditions"] == []
    assert a["read"] == "Audit read Live site v2 and found nothing to put right."
    assert got["workable"] is None and got["rubric"] == []


def test_w5_the_pane_draws_no_workable_line_and_no_pass_cell_for_a_clean_reading(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    J.audited(REF, 2, [])
    got, ctx = audit_of(mods)
    html = render(page_state(got), "renderAudit(s)")
    text = shown(html)
    assert "Workable (checked by code)" not in text and "Not workable yet" not in text
    assert not re.search(r">\s*PASS\s*<", html) and "PASS" not in text
    assert "Cycle 1 · site v2 · all pass" in text and "Audit read: Audit read Live site v2 and found nothing to put right." in text
    assert not re.search(r"undefined|NaN|\bnull\b|\[object", text)


def test_w5_a_reading_with_findings_has_a_row_for_each_finding_and_none_for_any_item(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    finding(W, R, [("index.html", "the page says 'to be confirmed' where the hours should be", "high"),
                   ("about.html", "the page says 'coming soon'", "high"), (None, "a link to the car park has no address", "low")])
    got, ctx = audit_of(mods)
    a = got["audits"][0]
    assert (a["cycle"], a["version"], a["all_pass"], a["read"]) == (1, 2, False, "")
    assert a["results"] == [], "no item was read one by one"
    assert [(r["id"], r["verdict"], r["pass"], r["note"], r["severity"]) for r in a["extra_issues"]] == [
        ("F-1", "NEEDS_REVISION", False, "index.html", "high"), ("F-2", "NEEDS_REVISION", False, "about.html", "high"),
        ("F-3", "NEEDS_REVISION", False, "", "low")]
    assert a["extra_issues"][0]["criterion"] == "the page says 'to be confirmed' where the hours should be"
    assert got["workable"] is None
    text = shown(render(page_state(got), "renderAudit(s)"))
    assert "failing" in text and "extra: the page says 'coming soon'" in text and "Workable" not in text
    assert text.count("NEEDS_REVISION") == 3


def test_w5_the_ledgers_event_beside_a_finding_post_does_not_make_a_second_entry(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    finding(W, R, [("index.html", "the page says 'coming soon'", "high")])
    event(J, "audit.finding_filed", "Audit", "Identity", "recorded", "the page says 'coming soon'", step=7,
          payload={"severity": "high", "findings": 1}, evidence_refs=[{"artifact": "Live site", "version": 2}])
    got, ctx = audit_of(mods)
    assert len(got["audits"]) == 1 and got["audits"][0]["all_pass"] is False


def test_w5_a_reading_that_was_not_read_is_no_entry(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    J.not_read(REF, 1, "it was not sampled")
    assert [e["action"] for e in J.events(REF)] == ["audit.not_read"]
    got, ctx = audit_of(mods)
    assert got["audits"] == [], "the page then prints its own empty text"
    text = shown(render(page_state(got), "renderAudit(s)"))
    assert "Audit checks the site against Identity's checklist after each cycle." in text


def test_w5_no_reading_at_all_is_no_entry_and_no_conditions(mods):
    got, ctx = audit_of(mods)
    assert got["audits"] == [] and got["conditions"] is None and got["workable"] is None and got["rubric"] == []


def test_w5_readings_are_numbered_oldest_first_across_both_kinds(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    finding(W, R, [("index.html", "a hole", "high")], about_version=1, at=ago(300))
    J.audited(REF, 2, [])
    got, ctx = audit_of(mods)
    assert [(a["cycle"], a["version"], a["all_pass"]) for a in got["audits"]] == [(1, 1, False), (2, 2, True)]


def test_w5_a_version_is_never_null(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    # the shape a1-audit files for a deliverable that is not a website: no evidence at all
    event(J, "audit.finding_filed", "Audit", "Identity", "recorded", "Audit read the result and found nothing to put right.", step=7,
          payload={"severity": "none", "findings": 0}, evidence_refs=[])
    post(W, R, "Audit", "Identity", "inform", {"word": "finding", "claim": "a hole", "findings": [{"claim": "a hole"}]}, thread="x-f")
    post(W, R, "Audit", "Identity", "inform", {"word": "finding", "claim": "x", "findings": [], "about_version": "v3?"}, thread="x-g")
    got, ctx = audit_of(mods)
    assert len(got["audits"]) == 3
    assert all(a["version"] is not None for a in got["audits"])
    assert sorted(str(a["version"]) for a in got["audits"]) == ["", "", ""]
    assert [r["id"] for a in got["audits"] for r in a["extra_issues"]] == ["F-1", "F-1"], "a claim alone is one finding"
    text = shown(render(page_state(got), "renderAudit(s)"))
    assert "vnull" not in text and "undefined" not in text and not re.search(r"\bnull\b", text)


def test_w5_a_clean_reading_whose_event_names_a_version_by_another_key_still_reads(mods):
    ctx = standin(mods, chat=False)
    ctx.events = [{"seq": 1, "action": "audit.finding_filed", "occurred_at": "2026-10-26T10:00:00+05:30", "summary": "",
                   "payload": {"severity": "none"}, "evidence_refs": [{"artifact": "Site", "version": 7}, None, "x"]}]
    a = K.build(ctx)["audits"][0]
    assert (a["version"], a["all_pass"]) == (7, True) and a["read"] == "Audit found nothing to put right."


def test_w5_every_string_is_in_the_owners_words_and_no_check_id(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    finding(W, R, [("index.html", "Priority granted the line; take the refusal to Identity", "high")])
    J.audited(REF, 3, [])
    got, ctx = audit_of(mods)
    text = json.dumps(got["audits"])
    assert not BANNED.search(text) and "granted" not in text
    assert not [s for s in walk(got["audits"]) if CHECK_ID.match(s)]
    assert json.loads(text) == got["audits"]


# ---- the conditions: the check engine's recorded check ---------------------------------------------------------------------
def test_w5_conditions_are_the_check_engines_notes_on_the_latest_build(mods):
    W, R, J, F = mods
    build_version(W, {"ok": False, "notes": ["a link does not resolve"]})
    build_version(W, {"ok": True, "notes": ["6 pages render, every link resolves", "the home page is there"]})
    got, ctx = audit_of(mods)
    assert got["conditions"] == [
        {"id": "N1", "text": "6 pages render, every link resolves", "met": True, "evidence": "Check engine, Build v2"},
        {"id": "N2", "text": "the home page is there", "met": True, "evidence": "Check engine, Build v2"}]


def test_w5_a_failed_check_is_one_condition_not_met_with_the_notes_as_evidence(mods):
    W, R, J, F = mods
    build_version(W, {"ok": False, "notes": ["a link does not resolve", "the home page is missing"]})
    got, ctx = audit_of(mods)
    assert got["conditions"] == [{"id": "N1", "text": "The build passes the Check engine's check", "met": False,
                                  "evidence": "a link does not resolve; the home page is missing"}]
    build_version(W, {"ok": False, "notes": []})
    ctx = standin(mods)
    assert K.build(ctx)["conditions"][0]["evidence"] == "its check failed"


def test_w5_a_pass_with_no_notes_is_one_condition_met(mods):
    W, R, J, F = mods
    build_version(W, {"ok": True, "notes": []})
    got, ctx = audit_of(mods)
    assert got["conditions"] == [{"id": "N1", "text": "The build passes the Check engine's check", "met": True,
                                  "evidence": "Check engine, Build v1"}]


def test_w5_no_version_with_a_check_is_no_conditions(mods):
    W, R, J, F = mods
    got, ctx = audit_of(mods)
    assert got["conditions"] is None
    build_version(W, {})
    ctx = standin(mods)
    assert K.build(ctx)["conditions"] is None, "an empty check is no check"


def test_w5_the_previewable_artifact_is_the_build_else_the_last_one_filed(mods):
    W, R, J, F = mods
    build_version(W, {"ok": True, "notes": ["fine"]}, art="Live site")
    assert K.build(standin(mods))["conditions"] is None, "the build has no version, and the live site is not what is previewed"
    ctx = standin(mods)                                        # a department whose line has no Build
    ctx.arts = [a for a in ctx.arts if a["name"] != "Build"]
    ctx.engines = [e for e in ctx.engines if e["writes"] != "Live site"]
    c = K.build(ctx)["conditions"]
    assert c == [{"id": "N1", "text": "fine", "met": True, "evidence": "Department, Live site v1"}]
    build_version(W, {"ok": False, "notes": []}, art="Live site")
    ctx = standin(mods)
    ctx.arts = [a for a in ctx.arts if a["name"] != "Build"]
    ctx.engines = [e for e in ctx.engines if e["writes"] != "Live site"]
    assert K.build(ctx)["conditions"][0]["text"] == "The live site passes the department's check"


def test_w5_the_pane_draws_the_conditions_with_their_count(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    J.audited(REF, 1, [])
    build_version(W, {"ok": True, "notes": ["6 pages render", "the home page is there"]})
    got, ctx = audit_of(mods)
    text = shown(render(page_state(got), "renderAudit(s)"))
    assert "Necessary conditions (checked by code, site v1): 2 of 2 met" in text
    assert "N1 6 pages render" in text and "Check engine, Build v1" in text and "MET" in text and "NOT MET" not in text


def test_w5_refs_and_audits_condensed(mods):
    W, R, J, F = mods
    ctx = standin(mods)
    assert X.refs(ctx) == {"conditions": {}, "rubric": {}} and X.audits_condensed(ctx) == []
    build_version(W, {"ok": True, "notes": ["6 pages render", "the home page is there"]})
    ctx = standin(mods)
    assert X.refs(ctx) == {"conditions": {"N1": "6 pages render", "N2": "the home page is there"}, "rubric": {}}
    assert X.audits_condensed(ctx) == []


def test_w5_the_builders_memoise_and_never_raise(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    J.audited(REF, 2, [])
    ctx = standin(mods)
    first = X.build_audits(ctx)
    assert X.build_audits(ctx) is first and X.build_conditions(ctx) is X.build_conditions(ctx)
    ctx = standin(mods)
    ctx.posts = None
    assert X.build_audits(ctx) == [] and any(r.startswith("audits: TypeError") for r in ctx.reasons), ctx.reasons
    ctx = standin(mods)
    ctx.arts = 5
    assert X.build_conditions(ctx) is None and any(r.startswith("conditions:") for r in ctx.reasons)
    assert X.refs(ctx) == {"conditions": {}, "rubric": {}}
    got = K.build(ctx)
    assert got["conditions"] is None and sorted(got) == sorted(K.KEYS)


def test_w5_an_offline_department_has_read_nothing_and_says_so(mods, born):
    W, R, J, F = mods
    ref = born()
    for a in [a for a in W.asks(ref) if a["status"] == "pending" and a["kind"] == "publish"]:
        W.decide_ask(ref, a["id"], True)
    W.run_until_idle(ref, limit=300)
    ctx = standin(mods, ref=ref)
    assert "audit.not_read" in [e["action"] for e in J.events(ref)], "no model was there to read it"
    got = K.build(ctx)
    assert got["audits"] == [] and got["workable"] is None
    assert got["conditions"] and all(c["met"] for c in got["conditions"]) and got["conditions"][0]["evidence"] == "Check engine, Build v1"
    assert not BANNED.search(json.dumps(got)) and not [s for s in walk(got) if CHECK_ID.match(s)]
