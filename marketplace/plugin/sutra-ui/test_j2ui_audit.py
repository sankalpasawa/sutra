"""test_j2ui_audit.py -- what Audit read, the recorded conditions, and the disagreements (j2ui_audit.py; UI port, package j2ui-work).

Named claims:
  W8  built on fixtures of the panes' new keys (the record's readings item by item, Root's standards, Priority's prices): with them
      the latest reading has a row for each item and workable becomes a list, the standards are conditions R-1 on, and Priority's
      own words refine what it said; with none of the keys every output is what W5 and W6 gave, byte for byte
  W6  one conflict for each bargain in which Priority asked for less or said no, and for each the two took to Identity; a
      straight yes is none. Each attempt says the act in the owner's words, as the chat does, and carries the chat's id of its
      post. It is settled by the two, by Identity's ruling, or by Identity after the owner's answer, and open until then.
  W5  the Audit tab is honest. A clean reading is one entry with a `read` line and no row for any item, because Sutra records no
      verdict for each item: the tab draws no 'Workable (checked by code)' and no PASS cell for a check nobody made. A reading
      with findings has a row for each finding. A reading that was not read is no entry. The conditions are the check engine's
      recorded check on the build, named for what they are, and none when no version has one. No version is ever null.

The helpers (the stand-in Ctx, the record's writers, the prototype's page rendered in node) are test_j2ui_work.py's.
"""
import json
import re
from pathlib import Path

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


def offline(monkeypatch, R, answers):
    """The AI inside answers these steps; every other step falls to its draft, as it does offline (test_functions_view.py's)."""
    monkeypatch.delenv("SUTRA_WEBSITE_OFFLINE", raising=False)
    monkeypatch.setattr(R, "MODEL", lambda prompt, step: (answers[step["id"]], 0.01, "model") if step["id"] in answers else (None, 0.0, "offline"))


NO = {"priority.bargain": {"answer": "reject", "why": "the envelope has no room today"}}
LESS = {"priority.bargain": {"answer": "counter", "why": "the envelope has room for three today", "keep": ["Plan", "Write", "Check"]}}
RUN = dict(NO, **{"identity.close": {"ruling": "run", "why": "the goal cannot be met without a site"}})
GOAL = "Build a website that teaches algebra to Class 8 students"


def clean_reading(J, version, artifact="Live site"):
    """What a reading that found nothing to put right leaves in the ledger: audit.finding_filed, severity none, naming what was
    read. Written as the event itself, so these tests do not depend on how j2_runtime.audited decides to write it."""
    return event(J, "audit.finding_filed", "Audit", "Identity", "recorded", "Audit read %s v%s and found nothing to put right." % (artifact, version),
                 step=7, payload={"severity": "none", "findings": 0}, evidence_refs=[{"artifact": artifact, "version": version}])


def build_version(W, check, art="Build", files=None):
    return W.VERS.add(W._abase(REF, art), files or {"index.html": "<p>x</p>"}, [], "r-x", check, W.now())


def audit_of(mods, **kw):
    ctx = standin(mods, **kw)
    return K.build(ctx), ctx


# ---- W5: audits ---------------------------------------------------------------------------------------------------------
def test_w5_a_clean_reading_is_one_entry_with_a_read_line_and_no_item_rows(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    clean_reading(J, 2)
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
    clean_reading(J, 2)
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
    clean_reading(J, 2)
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
    clean_reading(J, 3)
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
    clean_reading(J, 1)
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
    clean_reading(J, 2)
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


# ---- W6: conflicts --------------------------------------------------------------------------------------------------------
def conflicts_of(mods, ref=REF, **kw):
    ctx = standin(mods, ref=ref, **kw)
    return K.build(ctx)["conflicts"], ctx


def test_w6_a_plain_run_has_no_conflict(mods, born):
    ref = born()
    got, ctx = conflicts_of(mods, ref=ref)
    assert got == [] and ctx.reasons == []


def test_w6_no_bargain_at_all_is_no_conflict(mods):
    got, ctx = conflicts_of(mods)
    assert got == []


def test_w6_a_no_and_a_ruling_to_run(mods, born, monkeypatch):
    W, R, J, F = mods
    offline(monkeypatch, R, RUN)
    ref = born()
    got, ctx = conflicts_of(mods, ref=ref)
    assert len(got) == 1
    c = got[0]
    assert list(c) == ["id", "cycle", "topic", "between", "about", "subject", "detail", "attempts", "status", "escalated",
                       "attempts_before_escalation", "resolved_by", "identity", "escalated_to_user", "user_question", "user_answer",
                       "winner", "outcome", "priority_final", "adaptation_final", "attempts_used", "registered"]
    assert (c["id"], c["cycle"], c["topic"], c["between"], c["about"], c["detail"], c["winner"]) == ("C-1", 1, "proposal", ["adaptation", "priority"], None, None, None)
    assert c["subject"] == "the goal needs these workflows"
    assert [(a["n"], a["who"], a["position"], a["agree"]) for a in c["attempts"]] == [(0, "adaptation", "opening proposal", None), (1, "priority", "said no", False)]
    assert c["attempts"][0]["text"] == "Proposed the plan to Priority: " + GOAL
    assert c["attempts"][1]["text"] == "Said no to the plan: the envelope has no room today"
    assert (c["status"], c["escalated"], c["attempts_used"], c["attempts_before_escalation"]) == ("settled", True, 1, 1)
    assert c["resolved_by"] == "identity" and c["escalated_to_user"] is False and c["user_question"] is None and c["user_answer"] is None
    assert c["identity"] == [{"after_user": False, "resolved": True, "ruling": "it runs", "clause": "", "say": "the goal cannot be met without a site"}]
    assert c["outcome"] == "Identity ruled it runs." and c["registered"] == ["Plan", "Write", "Check", "Publish"]
    assert [n["name"] for n in c["adaptation_final"]] == ["Plan", "Write", "Check", "Publish"] and c["priority_final"] == []
    assert all(n["cost"] is None for n in c["adaptation_final"]), "no cost is recorded for a proposed workflow"


def test_w6_asked_for_less_then_a_yes_is_settled_by_the_two(mods, born, monkeypatch):
    W, R, J, F = mods
    offline(monkeypatch, R, LESS)
    ref = born()
    got, ctx = conflicts_of(mods, ref=ref)
    assert len(got) == 1
    c = got[0]
    assert [(a["n"], a["who"], a["position"], a["agree"]) for a in c["attempts"]] == [
        (0, "adaptation", "opening proposal", None), (1, "priority", "asked for less", False), (2, "adaptation", "said yes", True),
        (3, "priority", "said yes", True)]
    assert c["attempts"][1]["text"] == "Asked Adaptation for less: the envelope has room for three today"
    assert c["attempts"][3]["text"].startswith("Said yes to the plan: ")
    assert (c["status"], c["escalated"], c["resolved_by"], c["attempts_used"], c["attempts_before_escalation"]) == ("settled", False, "agents", 3, 0)
    assert c["identity"] == [] and c["user_question"] is None and c["escalated_to_user"] is False
    assert c["outcome"] == "Settled between the two: Priority said yes after asking for less."
    assert [n["name"] for n in c["adaptation_final"]] == ["Plan", "Write", "Check"] == [n["name"] for n in c["priority_final"]]
    assert c["registered"] == ["Plan", "Write", "Check"]


def test_w6_a_no_that_goes_to_the_owner_waits_for_the_owner_then_follows_the_answer(mods, born, monkeypatch):
    W, R, J, F = mods
    offline(monkeypatch, R, NO)
    ref = born()
    got, ctx = conflicts_of(mods, ref=ref)
    c = got[0]
    assert (c["status"], c["escalated"], c["resolved_by"], c["escalated_to_user"]) == ("open", True, None, True)
    assert c["identity"] == [{"after_user": False, "resolved": False, "ruling": "asked you", "clause": "", "say": "the goal and the rules do not settle it"}]
    assert c["user_question"]["options"] == ["Stamp", "Say no"] and "Priority said no to the plan: the envelope has no room today" in c["user_question"]["question"]
    assert "Stamp to run it as proposed, or say no to drop it." in c["user_question"]["question"]
    assert c["user_answer"] is None and c["outcome"] == "Waiting for your answer." and c["registered"] is None
    html = shown(render(page_state(K.build(ctx)), "renderConflicts(s)"))
    assert "asked you" in html and "Option 1: Stamp" in html and "Option 2: Say no" in html and "waiting" in html and "open" in html
    ask_id = next(a["id"] for a in W.asks(ref) if a["kind"] == "conflict")
    W.decide_ask(ref, ask_id, True)
    W.run_until_idle(ref, limit=300)
    got, ctx = conflicts_of(mods, ref=ref)
    c = got[0]
    assert (c["status"], c["resolved_by"], c["user_answer"]) == ("settled", "identity_after_user", "Stamp")
    assert [(r["after_user"], r["resolved"], r["ruling"]) for r in c["identity"]] == [(False, False, "asked you"), (True, True, "it runs")]
    assert c["outcome"] == "You stamped the plan as proposed." and c["registered"] == ["Plan", "Write", "Check", "Publish"]


def test_w6_the_owners_no_drops_the_plan(mods, born, monkeypatch):
    W, R, J, F = mods
    offline(monkeypatch, R, NO)
    ref = born()
    ask_id = next(a["id"] for a in W.asks(ref) if a["kind"] == "conflict")
    W.decide_ask(ref, ask_id, False)
    W.run_until_idle(ref, limit=300)
    got, ctx = conflicts_of(mods, ref=ref)
    c = got[0]
    assert (c["status"], c["resolved_by"], c["user_answer"], c["registered"]) == ("settled", "identity_after_user", "Say no", None)
    assert [(r["after_user"], r["ruling"], r["say"]) for r in c["identity"]] == [(False, "asked you", "the goal and the rules do not settle it"),
                                                                           (True, "dropped", "You said no to the plan.")]
    assert c["outcome"] == "You said no, so the plan is dropped."


def test_w6_no_string_says_an_inside_word_or_an_acts_id(mods, born, monkeypatch):
    W, R, J, F = mods
    for answers in (RUN, LESS, NO):
        offline(monkeypatch, R, answers)
        ref = born(org="Org %d" % len(answers))
        got, ctx = conflicts_of(mods, ref=ref)
        text = json.dumps(got)
        assert got and not BANNED.search(text), BANNED.findall(text)
        assert not re.search(r"\b(accept|reject)-proposal\b|granted|countered|refus", text), re.findall(r".{20}(?:granted|countered|refus).{20}", text)
        assert not [x for x in walk(got) if CHECK_ID.match(x)]
        assert json.loads(text) == got


def test_w6_each_attempt_carries_the_chat_id_of_its_post(mods, born, monkeypatch):
    W, R, J, F = mods
    offline(monkeypatch, R, LESS)
    ref = born()
    ctx = standin(mods, ref=ref)
    got = K.build(ctx)["conflicts"][0]
    posts = {p["n"]: p for p in ctx.posts}
    ids = [a["msg"] for a in got["attempts"]]
    assert all(isinstance(i, int) for i in ids) and ids == sorted(ids)
    for a in got["attempts"]:
        m = ctx.chat[a["msg"] - 1]
        assert m["id"] == a["msg"] and m["who"] == a["who"], (a, m)
    assert [ctx.msg_of[("b", n)] for n in sorted(posts) if posts[n]["payload"].get("word") == "line" and posts[n]["src"] in ("Adaptation", "Priority")] == ids


def test_w6_an_attempt_whose_post_has_no_chat_message_has_no_id(mods, born, monkeypatch):
    W, R, J, F = mods
    offline(monkeypatch, R, NO)
    ref = born()
    ctx = standin(mods, ref=ref, chat=False)
    got = K.build(ctx)["conflicts"][0]
    assert [a["msg"] for a in got["attempts"]] == [None, None]
    text = shown(render(page_state(K.build(ctx)), "renderConflicts(s)"))
    assert "[None]" not in text and "[null]" not in text


def test_w6_the_page_draws_the_conflict(mods, born, monkeypatch):
    W, R, J, F = mods
    offline(monkeypatch, R, RUN)
    ref = born()
    got, ctx = conflicts_of(mods, ref=ref)
    text = shown(render(page_state(K.build(ctx)), "renderConflicts(s)"))
    assert "C-1 · cycle 1 · Adaptation vs Priority · the goal needs these workflows" in text and "settled" in text
    assert "attempts 1 of 4 · escalated to Identity after 1" in text
    assert "resolved by Identity, from the charter" in text
    assert re.search(r"From the charter: ruled\s+it runs\s*\.\s*the goal cannot be met without a site", text), text
    assert "outcome Identity ruled it runs. · registered: Plan, Write, Check, Publish" in text
    assert "Said no to the plan: the envelope has no room today" in text and "said no" in text and "opening proposal" in text
    assert "Plan (?)" in text and "nothing" in text, "Priority's final position after a no is nothing"
    assert not re.search(r"undefined|NaN|\bnull\b|\[object|\[None\]", text)


# ---- the shapes the real flows above do not reach: boards written by hand ------------------------------------------------
def bargain(W, R, thread, steps, why="the goal needs these workflows"):
    """A bargain thread on the board: (src, act, payload[, at]) for each post, hops counting up."""
    engines = [{"name": n, "does": "x", "reads": "Brief", "writes": n, "internet": False} for n in ("Plan", "Write", "Check")]
    for hop, (src, act, extra, *at) in enumerate(steps, 1):
        dst = "Priority" if src == "Adaptation" else "Adaptation"
        payload = dict({"word": "line"}, **extra)
        if src == "Adaptation":
            payload.setdefault("engines", engines)
            payload.setdefault("why", why)
        post(W, R, src, dst, act, payload, thread=thread, hop=hop, at=at[0] if at else None)


def test_w6_a_straight_yes_is_not_a_conflict_and_an_unanswered_proposal_is_not_yet_one(mods):
    W, R, J, F = mods
    bargain(W, R, "x-yes", [("Adaptation", "propose", {}), ("Priority", "accept-proposal", {"why": "fits today"})])
    bargain(W, R, "x-wait", [("Adaptation", "propose", {})])
    got, ctx = conflicts_of(mods)
    assert got == []


def test_w6_a_counter_nobody_has_answered_is_open(mods):
    W, R, J, F = mods
    bargain(W, R, "x-1", [("Adaptation", "propose", {}), ("Priority", "propose", {"counter": True, "keep": ["Plan"], "why": "room for one"})])
    got, ctx = conflicts_of(mods)
    c = got[0]
    assert (c["status"], c["resolved_by"], c["escalated"], c["outcome"]) == ("open", None, False, "Waiting for Adaptation to answer Priority's ask for less.")
    assert [n["name"] for n in c["priority_final"]] == ["Plan"] and len(c["adaptation_final"]) == 3 and c["registered"] is None


def test_w6_a_no_nobody_has_taken_on_is_open(mods):
    W, R, J, F = mods
    bargain(W, R, "x-1", [("Adaptation", "propose", {}), ("Priority", "reject-proposal", {"why": "no room"})])
    got, ctx = conflicts_of(mods)
    assert (got[0]["status"], got[0]["outcome"], got[0]["escalated"]) == ("open", "Waiting for Identity.", False)


def test_w6_the_bargain_that_reached_its_bound_goes_to_identity_after_at_most_four(mods):
    W, R, J, F = mods
    cycle(W, "closing", 4)
    steps = [("Adaptation", "propose", {}), ("Priority", "propose", {"keep": ["Plan", "Write"], "why": "room for two"}),
             ("Adaptation", "propose", {}), ("Priority", "propose", {"keep": ["Plan"], "why": "room for one"}),
             ("Adaptation", "propose", {}), ("Priority", "propose", {"keep": [], "why": "no room"})]
    bargain(W, R, "x-1", steps)
    post(W, R, "Coordination", "Identity", "inform", {"word": "conflict", "why": "the bargain reached its bound", "bound": 4, "for": "x-1"}, thread="x-c")
    got, ctx = conflicts_of(mods)
    c = got[0]
    assert (c["attempts_used"], c["attempts_before_escalation"], c["escalated"], c["status"]) == (5, 4, True, "open")
    assert c["outcome"] == "Waiting for Identity." and c["escalated_to_user"] is False


def test_w6_a_conflict_post_with_no_bargain_on_the_board_is_still_a_conflict(mods):
    W, R, J, F = mods
    post(W, R, "Adaptation", "Identity", "inform", {"word": "conflict", "why": "Priority said no", "for": "x-gone"}, thread="x-c")
    got, ctx = conflicts_of(mods)
    c = got[0]
    assert c["attempts"] == [] and c["escalated"] and c["subject"] == "what to run" and c["adaptation_final"] == [] and c["priority_final"] == []


def test_w6_conflicts_are_numbered_by_when_their_bargains_began(mods):
    W, R, J, F = mods
    bargain(W, R, "x-b", [("Adaptation", "propose", {}), ("Priority", "reject-proposal", {"why": "no room"})])
    bargain(W, R, "x-a", [("Adaptation", "propose", {}), ("Priority", "propose", {"keep": ["Plan"], "why": "room for one"}),
                          ("Adaptation", "propose", {}), ("Priority", "accept-proposal", {"why": "fits"})])
    got, ctx = conflicts_of(mods)
    assert [c["id"] for c in got] == ["C-1", "C-2"] and [c["attempts_used"] for c in got] == [1, 3]
    assert [c["status"] for c in got] == ["open", "settled"]


def test_w6_the_owners_own_words_in_an_attempt_are_not_rewritten(mods):
    W, R, J, F = mods
    words = "Add a page that says we granted every request, and refused none"
    bargain(W, R, "x-1", [("Adaptation", "propose", {"words": words}), ("Priority", "reject-proposal", {"why": "no room"})])
    got, ctx = conflicts_of(mods)
    assert got[0]["attempts"][0]["text"] == "Proposed the plan to Priority: " + words


def test_w6_the_texts_are_the_chats_words_for_the_same_post(mods):
    W, R, J, F = mods
    bargain(W, R, "x-1", [("Adaptation", "propose", {}), ("Priority", "reject-proposal", {"why": "Priority refused the line"})])
    got, ctx = conflicts_of(mods)
    import functions_view
    for a, p in zip(got[0]["attempts"], [p for p in ctx.posts]):
        did = functions_view._did(p)
        assert a["text"].lower().startswith(did.lower()), (a["text"], did)
    assert got[0]["attempts"][1]["text"] == "Said no to the plan: Priority said no to the line"


def test_w6_a_conflicts_ruling_is_the_one_after_its_own_conflict_not_another_threads(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    bargain(W, R, "x-1", [("Adaptation", "propose", {}), ("Priority", "propose", {"keep": ["Plan"], "why": "room for one"}),
                          ("Adaptation", "propose", {}), ("Priority", "accept-proposal", {"why": "fits"})])
    bargain(W, R, "x-2", [("Adaptation", "propose", {}), ("Priority", "reject-proposal", {"why": "no room"})])
    post(W, R, "Adaptation", "Identity", "inform", {"word": "conflict", "why": "no room", "for": "x-2"}, thread="x-c2")
    event(J, "proposal.created", "Adaptation", "Priority", "pending", "Proposed", step=2, proposal_ref="x-1")
    event(J, "proposal.granted", "Priority", "Adaptation", "granted", "fits", step=3, proposal_ref="x-1")
    event(J, "conflict.raised", "Adaptation", "Identity", "waiting", "Priority said no", step=4, proposal_ref="x-2")
    event(J, "identity.ruled", "Identity", "Adaptation", "drop", "it cannot run", step=4, payload={"ruling": "drop", "workflow": []})
    got, ctx = conflicts_of(mods)
    first, second = got
    assert first["identity"] == [] and first["resolved_by"] == "agents" and first["escalated"] is False, "the ruling is not this bargain's"
    assert second["resolved_by"] == "identity" and second["identity"][0]["ruling"] == "dropped" and second["outcome"] == "Identity dropped the plan."


def test_w6_the_builder_memoises_and_never_raises(mods):
    ctx = standin(mods)
    first = X.build_conflicts(ctx)
    assert X.build_conflicts(ctx) is first
    ctx = standin(mods)
    ctx.posts = [{"n": 1, "src": "Adaptation", "dst": ["Priority"], "msg_type": "propose", "thread": "t", "payload": None}]
    got = K.build(ctx)
    assert sorted(got) == sorted(K.KEYS) and json.loads(json.dumps(got)) == got
    ctx = standin(mods)
    ctx.posts = 7
    assert K.build(ctx)["conflicts"] == [] and any(r.startswith("conflicts:") for r in ctx.reasons)


# ---- W8: what the panes add once the record holds it (fixtures: their shapes are the panes' own) ----------------------------------
import functions_view as FV                                    # the module j2ui_audit reads the panes through

LATEST_READING = {"artifact": "Live site", "v": 2, "at": "2026-10-26T21:20:00+05:30", "items": [
    {"id": "D1", "verdict": "met", "method": "code", "claim": "the record holds: every version has its run and its check",
     "evidence": "every version has its run and its check; the trace reaches the owner's words"},
    {"id": "D2", "verdict": "not_met", "method": "model", "claim": "the fees page names no fee", "evidence": "fees.html says to contact the office"},
    {"id": "D3", "verdict": "to_confirm", "method": "model", "claim": "it waits on a fact nobody has given: the clinic's opening hours",
     "evidence": "no hours are given in the brief or in anything filed"}]}
LATEST_DONE = {"artifact": "Live site", "v": 2, "at": "2026-10-26T21:20:00+05:30", "items": [
    {"id": "D1", "verdict": "met", "method": "model", "claim": "every ask is answered in the Result", "evidence": "result.md answers the one ask in full"}]}
ROOT_CHECKS = [{"summary": "The workflow meets Sutra's standards.", "at": "2026-10-26T21:00:00+05:30", "passed": True, "checks": [
    {"check": "names_an_engine", "says": "the workflow names its engines", "passed": True, "why": "the workflow names its engines"},
    {"check": "engines_known", "says": "each engine is one the Library has", "passed": True, "why": "Plan, Write, Check and Publish are in the Library"},
    {"check": "fits_room", "says": "Priority's room holds the plan", "passed": False, "why": "the plan costs more than today's room"}]}]


def panes(monkeypatch, **by_fn):
    """functions_view.function as the merged panes will answer it: {fn: its j2 part}; a function not named has none. Returns the
    list of the functions asked for, in order."""
    asked = []

    def function(ref, fn):
        asked.append(fn)
        return {"fn": fn, "j2": by_fn.get(fn, {})}
    monkeypatch.setattr(FV, "function", function)
    return asked


def clean_and_finding(mods, version=2):
    W, R, J, F = mods
    cycle(W, "running", 6)
    finding(W, R, [("fees.html", "the fees page names no fee", "high")], about_version=version)


def test_w8_the_latest_reading_gets_a_row_for_each_item_and_workable_lists_what_is_not_met(mods, monkeypatch):
    clean_and_finding(mods)
    panes(monkeypatch, audit={"latest": LATEST_READING})
    got, ctx = audit_of(mods)
    a = got["audits"][-1]
    assert [(r["id"], r["item"], r["verdict"], r["pass"]) for r in a["results"]] == [
        ("D1", 1, "PASS", True), ("D2", 2, "NEEDS_REVISION", False), ("D3", 3, "NEEDS_REVISION", False)]
    assert a["results"][0] == {"id": "D1", "item": 1, "criterion": "the record holds: every version has its run and its check", "verdict": "PASS",
                               "pass": True, "note": "every version has its run and its check; the trace reaches the owner's words"}
    assert a["results"][1]["note"] == "fees.html says to contact the office" and "needs_requester_fact" not in a["results"][1]
    assert a["results"][2]["needs_requester_fact"] == "it waits on a fact nobody has given: the clinic's opening hours"
    assert a["results"][2]["note"] == "to confirm with you: no hours are given in the brief or in anything filed"
    assert a["all_pass"] is False and [r["id"] for r in a["extra_issues"]] == ["F-1"], "Audit's finding stays beside the items"
    assert got["workable"] == ["the fees page names no fee", "to confirm with you: it waits on a fact nobody has given: the clinic's opening hours"]
    text = shown(render(page_state(got), "renderAudit(s)"))
    assert "Not workable yet (checked by code)" in text and "D2 2. the fees page names no fee" in text and "NEEDS_REVISION" in text


def test_w8_every_item_met_is_all_pass_and_workable_is_empty(mods, monkeypatch):
    W, R, J, F = mods
    cycle(W, "running", 6)
    clean_reading(J, 2)
    panes(monkeypatch, audit={"latest": LATEST_DONE})
    got, ctx = audit_of(mods)
    a = got["audits"][-1]
    assert a["all_pass"] is True and [(r["id"], r["verdict"]) for r in a["results"]] == [("D1", "PASS")]
    assert got["workable"] == []
    html = render(page_state(got), "renderAudit(s)")
    text = shown(html)
    assert "Workable (checked by code)" in text and "Not workable yet" not in text and re.search(r">\s*PASS\s*<", html)


def test_w8_a_clean_event_with_an_item_not_met_is_not_all_pass(mods, monkeypatch):
    W, R, J, F = mods
    cycle(W, "running", 6)
    clean_reading(J, 2)
    panes(monkeypatch, audit={"latest": LATEST_READING})
    a = audit_of(mods)[0]["audits"][-1]
    assert a["all_pass"] is False and len(a["results"]) == 3


def test_w8_with_no_reading_item_by_item_the_tab_stays_as_honest_as_before(mods, monkeypatch):
    W, R, J, F = mods
    cycle(W, "running", 6)
    clean_reading(J, 2)
    for view in ({}, {"latest": None}, {"latest": {}}, {"latest": {"items": []}}, {"latest": {"v": 2, "items": [{"id": "D1", "verdict": "unknown"}]}},
                 {"latest": "x"}, {"latest": {"items": "x"}}):
        panes(monkeypatch, audit=view)
        got, ctx = audit_of(mods)
        assert got["audits"][0]["results"] == [] and got["workable"] is None, view
        assert "Workable" not in shown(render(page_state(got), "renderAudit(s)"))


def test_w8_a_verdict_is_never_put_against_a_reading_it_was_not_made_on(mods, monkeypatch):
    clean_and_finding(mods, version=3)
    panes(monkeypatch, audit={"latest": LATEST_READING})                      # the pane's latest is of v2, the newest entry of v3
    got, ctx = audit_of(mods)
    assert got["audits"][-1]["results"] == [] and got["workable"] is None
    ctx2 = standin(mods)
    ctx2.posts, ctx2.events = [], []
    got = K.build(ctx2)
    assert got["audits"] == [] and got["workable"] is None, "no entry is made for a reading the tab does not otherwise know"


def test_w8_an_entry_with_no_version_takes_the_latest_readings(mods, monkeypatch):
    W, R, J, F = mods
    cycle(W, "running", 6)
    post(W, R, "Audit", "Identity", "inform", {"word": "finding", "claim": "a hole", "findings": [{"claim": "a hole"}]}, thread="x-f")
    panes(monkeypatch, audit={"latest": LATEST_READING})
    got, ctx = audit_of(mods)
    assert got["audits"][-1]["version"] == "" and len(got["audits"][-1]["results"]) == 3


def test_w8_the_pane_is_read_once_and_only_when_there_is_a_reading(mods, monkeypatch):
    asked = panes(monkeypatch, audit={"latest": LATEST_READING})
    audit_of(mods)
    assert asked.count("audit") == 0, "no reading, nothing to refine"
    clean_and_finding(mods)
    asked.clear()
    ctx = standin(mods)
    K.build(ctx)
    K.build(ctx)
    X.build_workable(ctx)
    assert asked.count("audit") == 1, asked


def test_w8_roots_standards_are_conditions_r_1_on(mods, monkeypatch):
    W, R, J, F = mods
    build_version(W, {"ok": True, "notes": ["6 pages render"]})
    panes(monkeypatch, adaptation={"root_checks": ROOT_CHECKS})
    got, ctx = audit_of(mods)
    assert got["conditions"] == [
        {"id": "N1", "text": "6 pages render", "met": True, "evidence": "Check engine, Build v1"},
        {"id": "R-1", "text": "the workflow names its engines", "met": True, "evidence": "Root's check: the workflow names its engines"},
        {"id": "R-2", "text": "each engine is one the Library has", "met": True, "evidence": "Root's check: Plan, Write, Check and Publish are in the Library"},
        {"id": "R-3", "text": "Priority's room holds the plan", "met": False, "evidence": "Root's check: the plan costs more than today's room"}]
    assert X.refs(ctx)["conditions"]["R-3"] == "Priority's room holds the plan"
    assert not [s for s in walk(got["conditions"]) if CHECK_ID.match(s)], "the standard's id is not shown"


def test_w8_roots_standards_stand_alone_when_the_check_engine_recorded_nothing(mods, monkeypatch):
    panes(monkeypatch, adaptation={"root_checks": ROOT_CHECKS})
    got, ctx = audit_of(mods)
    assert [c["id"] for c in got["conditions"]] == ["R-1", "R-2", "R-3"]


def test_w8_only_the_latest_review_counts_and_only_a_plan_that_is_registered(mods, monkeypatch):
    older = {"summary": "Root's check sent the plan back", "at": "2026-10-26T20:00:00+05:30", "passed": False,
             "checks": [{"check": "one_output", "says": "each engine writes something not yet written", "passed": False, "why": "Plan and Write write the same"}]}
    panes(monkeypatch, adaptation={"root_checks": [older] + ROOT_CHECKS})
    got, ctx = audit_of(mods)
    assert [c["id"] for c in got["conditions"]] == ["R-1", "R-2", "R-3"] and "each engine writes" not in json.dumps(got["conditions"])
    got, ctx = audit_of(mods, planned=False)
    assert got["conditions"] is None, "before Root's check registers a plan, there are no standards to show"


def test_w8_a_standard_with_no_sentence_says_what_it_found_and_one_with_neither_is_not_shown(mods, monkeypatch):
    review = dict(ROOT_CHECKS[0], checks=[
        {"check": "workflow_meets_standards", "says": "workflow_meets_standards", "passed": True, "why": "the workflow fits the workflow schema"},
        {"check": "engines_known", "says": "", "passed": True}, {"check": "names_unique", "passed": True, "why": "workflow_meets_standards"},
        {"check": "one_output", "says": "each engine writes something not yet written", "passed": False}, "x", None])
    panes(monkeypatch, adaptation={"root_checks": [review, "x"]})
    got, ctx = audit_of(mods)
    assert got["conditions"] == [
        {"id": "R-1", "text": "the workflow fits the workflow schema", "met": True, "evidence": "Root's check: the workflow fits the workflow schema"},
        {"id": "R-2", "text": "each engine writes something not yet written", "met": False, "evidence": "Root's check: it did not hold"}]


def seed_bargain(mods):
    W, R, J, F = mods
    bargain(W, R, "x-1", [("Adaptation", "propose", {}, T0), ("Priority", "propose", {"keep": ["Plan"], "why": "Priority countered the line"}, T1),
                          ("Adaptation", "propose", {}, T2), ("Priority", "accept-proposal", {"why": "granted"}, T3)])


def attempts_with_prices(mods, monkeypatch, prices):
    panes(monkeypatch, priority={"prices": prices})
    got, ctx = conflicts_of(mods)
    return [a["text"] for a in got[0]["attempts"]], got[0], ctx


T0, T1, T2, T3 = ("2026-10-26T10:00:0%d+05:30" % n for n in range(4))


def test_w8_prioritys_own_words_refine_what_it_said(mods, monkeypatch):
    seed_bargain(mods)
    prices = [{"at": T3, "said": "said yes", "why": "fits today: about 3 calls of the 960 left", "proposal": "line", "answer": "accept"},
              {"at": T1, "said": "asked for less", "why": "room for one workflow today", "proposal": "line", "answer": "counter"}]       # newest first
    texts, c, ctx = attempts_with_prices(mods, monkeypatch, prices)
    assert texts[0].startswith("Proposed the plan to Priority: ") and texts[2].startswith("Proposed the plan to Priority: ")
    assert texts[1] == "Asked Adaptation for less: room for one workflow today"
    assert texts[3] == "Said yes to the plan: fits today: about 3 calls of the 960 left"
    assert [a["position"] for a in c["attempts"]] == ["opening proposal", "asked for less", "said yes", "said yes"], "the position is the post's"


def test_w8_a_price_that_said_something_else_or_came_much_later_changes_nothing(mods, monkeypatch):
    seed_bargain(mods)
    base, c0, ctx = attempts_with_prices(mods, monkeypatch, [])
    prices = [{"at": T1, "said": "said no", "why": "no room"},                                        # another answer at the right time
              {"at": "2026-10-26T10:01:00+05:30", "said": "asked for less", "why": "a minute later"},   # the right answer, too late
              {"at": T3, "said": "said yes", "why": ""}, {"at": None, "said": "said yes", "why": "x"}, {"said": "said yes"}, "x"]
    texts, c, ctx = attempts_with_prices(mods, monkeypatch, prices)
    assert texts == base and c == c0


def test_w8_one_price_refines_one_answer(mods, monkeypatch):
    W, R, J, F = mods
    bargain(W, R, "x-1", [("Adaptation", "propose", {}, T0), ("Priority", "reject-proposal", {"why": "no room"}, T1)])
    bargain(W, R, "x-2", [("Adaptation", "propose", {}, T0), ("Priority", "reject-proposal", {"why": "no room either"}, T1)])
    panes(monkeypatch, priority={"prices": [{"at": T1, "said": "said no", "why": "the envelope has no room today"}]})
    got, ctx = conflicts_of(mods)
    assert [c["attempts"][1]["text"] for c in got] == ["Said no to the plan: the envelope has no room today", "Said no to the plan: no room either"]


def test_w8_the_prices_are_read_only_when_a_bargain_has_a_priority_answer(mods, monkeypatch):
    W, R, J, F = mods
    asked = panes(monkeypatch, priority={"prices": []})
    bargain(W, R, "x-1", [("Adaptation", "propose", {}, T0)])
    X.build_conflicts(standin(mods))
    assert asked == []
    bargain(W, R, "x-2", [("Adaptation", "propose", {}, T0), ("Priority", "reject-proposal", {"why": "no room"}, T1)])
    X.build_conflicts(standin(mods))
    assert asked == ["priority"]


def scenario(mods):
    """A department with every kind of thing the three enrichments touch: a reading, a Build check, a plan, and a bargain."""
    W, R, J, F = mods
    cycle(W, "running", 6)
    finding(W, R, [("fees.html", "the fees page names no fee", "high")])
    clean_reading(J, 3)
    build_version(W, {"ok": True, "notes": ["6 pages render"]})
    bargain(W, R, "x-1", [("Adaptation", "propose", {}, T0), ("Priority", "propose", {"keep": ["Plan"], "why": "room for one"}, T1),
                          ("Adaptation", "propose", {}, T2), ("Priority", "accept-proposal", {"why": "fits"}, T3)])


def test_w8_with_none_of_the_keys_every_output_is_what_w5_and_w6_gave(mods, monkeypatch):
    scenario(mods)
    plain_ctx = standin(mods)
    expected = K.build(plain_ctx)                                              # the panes of main: no latest, no checks, no prices
    for view in ({}, {"readings": [], "findings": [], "spot_checks": []}, {"latest": None, "root_checks": [], "prices": []},
                 {"proposal": None, "root_checks": [{"summary": "x", "at": None, "passed": True}], "rounds": []}):
        panes(monkeypatch, audit=view, adaptation=view, priority=view)
        got = K.build(standin(mods))
        assert got == expected and json.dumps(got, sort_keys=True) == json.dumps(expected, sort_keys=True), view
    assert expected["workable"] is None and expected["conditions"] == [
        {"id": "N1", "text": "6 pages render", "met": True, "evidence": "Check engine, Build v1"}]


def test_w8_a_pane_that_fails_or_answers_nothing_leaves_the_output_as_it_was(mods, monkeypatch):
    scenario(mods)
    expected = K.build(standin(mods))

    def boom(ref, fn):
        raise ValueError("no function named %s" % fn)
    monkeypatch.setattr(FV, "function", boom)
    ctx = standin(mods)
    got = K.build(ctx)
    assert got == expected and any(r.startswith("audit pane: ValueError") for r in ctx.reasons), ctx.reasons
    monkeypatch.setattr(FV, "function", lambda ref, fn: None)
    assert K.build(standin(mods)) == expected
    monkeypatch.setattr(FV, "function", lambda ref, fn: {"j2": "not a dict"})
    assert K.build(standin(mods)) == expected


def test_w8_everything_added_is_json_and_in_the_owners_words(mods, monkeypatch):
    scenario(mods)
    panes(monkeypatch, audit={"latest": dict(LATEST_READING, v=3)}, adaptation={"root_checks": ROOT_CHECKS},
          priority={"prices": [{"at": T1, "said": "asked for less", "why": "Priority countered the line"}]})
    got, ctx = audit_of(mods)
    text = json.dumps({k: got[k] for k in ("audits", "conditions", "conflicts", "workable")})
    assert len(got["audits"][-1]["results"]) == 3 and len(got["conditions"]) == 4 and got["conflicts"]
    assert not BANNED.search(text)
    assert not [s for s in walk(got) if CHECK_ID.match(s)] and json.loads(json.dumps(got)) == got
    assert got["conflicts"][0]["attempts"][1]["text"] == "Asked Adaptation for less: Priority asked for less on the line"


def test_w8_the_audit_layers_own_fixture_reads_as_these_stubs_do(mods, monkeypatch):
    """The panes' shapes are the layers' (schemas/layers/fixtures/view.audit.v1.json, from package a1-audit): once that fixture is
    on this branch, its four states are read here as the audit pane will give them."""
    f = Path(__file__).resolve().parent / "schemas" / "layers" / "fixtures" / "view.audit.v1.json"
    if not f.exists():
        pytest.skip("the Audit layer's fixture (package a1-audit) is not on this branch yet")
    states = json.loads(f.read_text())["view.audit"]
    W, R, J, F = mods
    cycle(W, "running", 6)
    finding(W, R, [("fees.html", "the fees page names no fee", "high")], about_version=states["reading"]["latest"]["v"])
    panes(monkeypatch, audit=states["reading"])
    got, ctx = audit_of(mods)
    assert [r["id"] for r in got["audits"][-1]["results"]] == ["D1", "D2", "D3"] and len(got["workable"]) == 2
    for name in ("empty", "not_read"):
        panes(monkeypatch, audit=states[name])
        got, ctx = audit_of(mods)
        assert got["audits"][-1]["results"] == [] and got["workable"] is None, name


# ---- W8 against the real panes: they run when the layers that add the keys are on this branch, and skip until then -------------
def real_pane(fn, key, ref=REF):
    got = (FV.function(ref, fn) or {}).get("j2") or {}
    if key not in got:
        pytest.skip("the %s pane has no '%s' on this branch yet (waiting on its layer)" % (fn, key))
    return got


def test_w8_real_audit_pane_a_reading_item_by_item_gets_its_rows(mods):
    W, R, J, F = mods
    cycle(W, "running", 6)
    real_pane("audit", "latest")
    finding(W, R, [("fees.html", "the fees page names no fee", "high")], about_version=1)
    item = {"subject": "x", "evidence": "fees.html says to contact the office", "method": "model", "severity": "low"}
    W.append_row(REF, "readings.jsonl", {"schema_version": 1, "id": "r-%08x" % 1, "v": 1, "artifact": "Live site", "cycle_id": None, "round": None,
                                         "read": True, "why_not_read": None, "findings": [], "at": W.now(),
                                         "items": [dict(item, id="D1", claim="the home page names the clinic", verdict="met"),
                                                   dict(item, id="D2", claim="the fees page names no fee", verdict="not_met")]})
    got, ctx = audit_of(mods)
    a = got["audits"][-1]
    assert [(r["id"], r["verdict"], r["pass"]) for r in a["results"]] == [("D1", "PASS", True), ("D2", "NEEDS_REVISION", False)]
    assert a["all_pass"] is False and got["workable"] == ["the fees page names no fee"]
    assert "Not workable yet (checked by code)" in shown(render(page_state(got), "renderAudit(s)"))


def test_w8_real_adaptation_pane_roots_standards_are_conditions(mods, born):
    W, R, J, F = mods
    ref = born()
    pane = real_pane("adaptation", "root_checks", ref)
    if not (pane["root_checks"] and pane["root_checks"][-1].get("checks")):
        pytest.skip("Adaptation's pane does not carry Root's checks on this branch yet")
    got = K.build(standin(mods, ref=ref))
    rows = [c for c in got["conditions"] if c["id"].startswith("R-")]
    checks = pane["root_checks"][-1]["checks"]
    assert len(rows) == len(checks) >= 1 and all(c["met"] for c in rows) and all(c["evidence"].startswith("Root's check: ") for c in rows)
    assert [c["text"] for c in rows] == [A_plain(c["says"]) or A_plain(c["why"]) for c in checks]
    assert not [s for s in walk(got["conditions"]) if CHECK_ID.match(s)] and not BANNED.search(json.dumps(got["conditions"]))


def A_plain(text):
    import j2ui_atoms
    return j2ui_atoms.plain(text)


def test_w8_real_priority_pane_prices_leave_the_bargain_in_the_owners_words(mods, born, monkeypatch):
    W, R, J, F = mods
    offline(monkeypatch, R, LESS)
    ref = born()
    real_pane("priority", "prices", ref)
    with_prices = K.build(standin(mods, ref=ref))["conflicts"]
    monkeypatch.setattr(FV, "function", lambda r, fn: {"j2": {}})
    without = K.build(standin(mods, ref=ref))["conflicts"]
    assert with_prices and with_prices == without, "Priority's own words are the post's own: the same sentence, said once"
    assert not BANNED.search(json.dumps(with_prices))


def test_w6_the_helpers_the_chat_and_the_tab_share_are_still_functions_views(mods):
    """The act in the owner's words is functions_view's own (_did, _said, _short) and the rulings' words are RULING_SAYS: the chat
    (j2ui_chat) and this tab say the same thing for the same post only while both read them there. A package that renames one
    must change both."""
    import functions_view
    for name in ("_did", "_said", "_short"):
        assert callable(getattr(functions_view, name)), name
    assert set(functions_view.RULING_SAYS) >= {"run", "drop", "ask"}
    post_ = {"n": 1, "src": "Priority", "dst": ["Adaptation"], "msg_type": "reject-proposal", "payload": {"word": "line", "why": "no room"}}
    assert functions_view._did(post_) == "said no to the plan" and functions_view._said(post_) == "no room"
    assert functions_view._short("x" * 300).endswith("…") and len(functions_view._short("x" * 300)) == 140
