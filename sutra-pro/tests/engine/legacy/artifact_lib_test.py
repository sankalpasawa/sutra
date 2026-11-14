"""Offline checks of the content door's pure logic (j2_artifact_lib.py): python artifact_lib_test.py

A fixture source run and a run template in temp folders; source_section (found, no source, unreadable), the door
(every row of the rule table), the draft with the source business slotted, the flag implications, the Artifacts rows.
No AI calls, nothing written outside the temp folders.
"""
import json
import os
import shutil
import sys
import tempfile

os.environ["STUDIO_MOCK"] = "1"
TMP = tempfile.mkdtemp(prefix="j2-artlib-")
os.environ["J2_LIBRARY_DIR"] = os.path.join(TMP, "library")
os.environ["J2_RUNS_DIR"] = os.path.join(TMP, "runs")
for k in ("J2_ARTIFACT_LIBRARY", "J2_AUTO_REUSE", "J2_TEMPLATE_LIBRARY", "J2_RUN_TEMPLATES", "J2_ARTIFACT_SCHEMA"):
    os.environ.pop(k, None)
from sutra_app.engine import j2_artifact_lib as A      # noqa: E402  (engine port: the vendored engine, not J2's flat modules)
from sutra_app.engine import j2_template_lib as L      # noqa: E402
from sutra_app.engine import j2_artifacts              # noqa: E402
from sutra_app.engine import j2                        # noqa: E402

passed = 0
SRC = "j2-20260101-000000"
DATA = {"goals": [{"id": "G1", "text": "Visitors see the classes of Still Point Yoga"}], "assumptions": []}
FP = "fp-same-inputs"


def ok(cond, label):
    global passed
    if not cond:
        shutil.rmtree(TMP, ignore_errors=True)
        sys.exit(f"FAIL: {label}")
    passed += 1


def put(d, name, obj):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        if name.endswith(".jsonl"):
            f.writelines(json.dumps(x) + "\n" for x in obj)
        else:
            json.dump(obj, f, indent=1)


def source_run(rid=SRC, audit_pass=True, data=DATA):
    d = os.path.join(TMP, "runs", rid)
    put(d, "goal.json", {"statement": "A site for Still Point Yoga", "site_name": "Still Point Yoga", "business_type": "yoga studio",
                         "facts": ["Still Point Yoga", "Monday 7:00 am Gentle Flow 500"], "done_when": ["Goals listed"]})
    put(d, "templates.json", {"schema": L.SCHEMA, "decisions": [
        {"workflow": "W-1", "atom": "W-1.a1", "artifact": "prd", "section": "Goals", "template": "Still Point Yoga Goals", "version": 2,
         "action": "created", "fingerprint": FP, "facts": 2, "template_workflow": "W-1"}]})
    put(d, "prd.json", {"schema": "artifact-schema/1", "artifact": "prd", "version": 1, "sections": {"Goals": data}})
    put(d, "stage-prd.json", {"stage": "prd", "goal": {}, "audits": [{"all_pass": audit_pass, "results": [{"pass": audit_pass}]}], "sections": {}})
    put(d, "summary.json", {"output_type": "prd", "status": "done", "done_when": [{"item": 1, "pass": True}]})
    put(d, "receipts.jsonl", [{"atom": "W-1.a1", "check": "artifact-schema", "pass": True, "attempt": 1},
                              {"atom": "W-1.a1", "check": "Goals listed", "pass": False, "attempt": 1},
                              {"atom": "W-1.a1", "check": "Goals listed", "pass": True, "attempt": 2},
                              {"atom": "W-1.a1", "check": "artifact-rules", "pass": True, "attempt": 2}])
    return d


def template(tid="a-yoga-rerun", made_from_run=SRC, made_from="W-1"):
    rt = L.RunTemplate.model_validate({
        "schema": L.RUN_TEMPLATE_SCHEMA, "id": tid, "name": tid, "description": "", "business_type": "yoga studio",
        "made_from_run": made_from_run, "mock": True, "stages": ["prd"],
        "workflows": [{"key": "W-1", "name": "PRD Goals section", "stage": "prd", "artifact": "prd", "section": "Goals",
                       "section_template": "Still Point Yoga Goals@2", "section_template_kind": "specialised",
                       "depends_on": [], "covers": ["Goals listed"], "made_from": made_from, "fix": False}],
        "facts_slots": [], "made_by": {}, "used_by": [], "created": ""})
    L.save_run_template(rt)
    return rt


try:
    # 1. the flag and what it implies
    ok(not A.enabled() and not L.auto_reuse() and not L.enabled() and not j2.artifact_schema_on(), "all off by default")
    os.environ["J2_ARTIFACT_LIBRARY"] = "1"
    ok(A.enabled() and L.auto_reuse() and L.enabled() and j2.run_templates_on() and j2.auto_reuse_on() and j2.artifact_schema_on(),
       "J2_ARTIFACT_LIBRARY=1 implies auto-reuse, the template library, run templates and the artifact schema")
    os.environ.pop("J2_ARTIFACT_LIBRARY")

    # 2. source_section: found, with its decision, audit and receipts
    source_run()
    rt = template()
    s = A.source_section(rt.id, "W-1", "prd", "Goals")
    ok(s and s["run"] == SRC and s["workflow"] == "W-1" and s["data"] == DATA and s["template"] == "Still Point Yoga Goals@2"
       and s["fingerprint"] == FP and s["audit"] == "pass", f"source section found: {s}")
    ok(s["receipts_passed"] == ["Goals listed", "artifact-rules"], f"the passing checks of the last attempt only: {s['receipts_passed']}")
    ok(s["sha"] == L.sha_of(DATA) and s["dir"].endswith(SRC), "sha and dir")
    # no source: a key the template lacks, a section the source did not write
    ok(A.source_section(rt.id, "W-9", "prd", "Goals") is None, "a key the template has no workflow for: None")
    ok(A.source_section(rt.id, "W-1", "prd", "Users") is None, "a section the source did not write: None")
    ok(A.source_section(rt.id, "W-1", "hld", "Goals") is None, "another artifact type: None")
    # unreadable: the run folder missing, a file broken, the template missing
    rt2 = template("gone-run", made_from_run="j2-20260101-999999")
    try:
        A.source_section(rt2.id, "W-1", "prd", "Goals")
        ok(False, "a missing source run must raise SourceUnreadable")
    except A.SourceUnreadable as e:
        ok("not in the runs folder" in str(e), f"missing run: {e}")
    broken = source_run("j2-20260102-000000")
    open(os.path.join(broken, "prd.json"), "w", encoding="utf-8").write("{not json")
    rt3 = template("broken-run", made_from_run="j2-20260102-000000")
    try:
        A.source_section(rt3.id, "W-1", "prd", "Goals")
        ok(False, "broken JSON must raise SourceUnreadable")
    except A.SourceUnreadable as e:
        ok("cannot be read" in str(e), f"broken file: {e}")
    try:
        A.source_section("no-such-template", "W-1", "prd", "Goals")
        ok(False, "a missing template must raise SourceUnreadable")
    except A.SourceUnreadable:
        ok(True, "missing template")

    # 3. the door, every row
    need = {"fingerprint": FP}
    rec = {"action": "reused", "template": "Still Point Yoga Goals", "version": 2}
    d = A.door(need, rec, s)
    ok((d["door"], d["rule"]) == ("reuse", "same") and d["source"]["run"] == SRC and "data" not in d["source"], f"same inputs: {d}")
    d = A.door({"fingerprint": "other"}, rec, s)
    ok((d["door"], d["rule"]) == ("reuse", "cross"), f"router reused, other inputs, no charter given: cross-client reuse: {d}")
    d = A.door({"fingerprint": "other"}, rec, s, goal={"site_name": "Flow Pilates", "facts": ["Flow Pilates"]})
    ok((d["door"], d["rule"]) == ("adapt", "cross-facts") and "1 value" in d["reason"],
       f"the section names Still Point Yoga, which this charter lacks: adapt, not served: {d}")
    d = A.door({"fingerprint": "other"}, rec, s, goal={"site_name": "Still Point Yoga", "facts": ["Still Point Yoga"]})
    ok((d["door"], d["rule"]) == ("reuse", "cross"), "the same values in this charter: served")
    ok(A.foreign_values(s, {"site_name": "Flow Pilates"}) == ["Still Point Yoga"], "foreign values named")
    clean = {**s, "data": {"goals": [{"id": "G1", "text": "Visitors see the weekly classes"}], "assumptions": []}}
    ok(A.foreign_values(clean, {"site_name": "Flow Pilates"}) == [] and A.door({"fingerprint": "x"}, rec, clean, goal={"site_name": "Flow Pilates"})["rule"] == "cross",
       "a section with no value of its business is served for another client")
    d = A.door(need, {**rec, "version": 3}, s)
    ok((d["door"], d["rule"]) == ("reuse", "cross"), "same fingerprint but another template version: cross, not same")
    d = A.door({"fingerprint": "other"}, {**rec, "action": "extended"}, s)
    ok((d["door"], d["rule"]) == ("adapt", "near"), f"router extended: adapt: {d}")
    for act in ("created", "generic", ""):
        d = A.door({"fingerprint": "other"}, {**rec, "action": act}, s)
        ok((d["door"], d["rule"]) == ("build", "new"), f"router {act or 'nothing'}: build")
    d = A.door(need, rec, None)
    ok((d["door"], d["rule"]) == ("build", "none") and d["source"] is None, "no source section: build")
    d = A.door(need, rec, None, has_key=False)
    ok((d["door"], d["rule"]) == ("build", "none") and "no run template" in d["reason"], "no key: build, says why")
    d = A.door(need, rec, s, error="source run x is not in the runs folder")
    ok((d["door"], d["rule"]) == ("unknown", "0") and d["source"] is None, f"unreadable: unknown, never build-for-nothing: {d}")
    failed_src = {**s, "audit": "fail"}
    d = A.door(need, rec, failed_src)
    ok((d["door"], d["rule"]) == ("build", "audit"), "a source stage whose audit failed is not served")
    ok(set(A.counts([{"door": "reuse"}, {"door": "reuse"}, {"door": "x"}]).items()) == {("reuse", 2), ("adapt", 0), ("build", 0), ("unknown", 0)}, "counts")

    # 4. stage_audit from the summary when no stage file, and "not recorded"
    d2 = source_run("j2-20260103-000000")
    os.remove(os.path.join(d2, "stage-prd.json"))
    ok(A.stage_audit(d2, "prd") == "pass", "audit from the summary when the stage file is missing")
    put(d2, "summary.json", {"output_type": "hld", "status": "done"})
    ok(A.stage_audit(d2, "prd") == "not recorded", "another stage's summary says nothing")

    # 5. the draft: the source business's values slotted, nothing else changed
    text = A.draft_text(s)
    ok("Still Point Yoga" not in text and "<site name>" in text and "G1" in text, f"draft slotted: {text[:120]}")

    # 6. the chat line and the record
    ok("served" in A.chat_line({"workflow": "W-3", "door": "reuse", "rule": "same", "section": "Goals", "source": {"run": SRC, "workflow": "W-1"}})
       and "drafting" in A.chat_line({"workflow": "W-3", "door": "adapt", "section": "Goals", "source": {"run": SRC, "workflow": "W-1"}, "reason": ""})
       and "built" in A.chat_line({"workflow": "W-3", "door": "build", "reason": "x", "section": "Goals"}), "chat lines")
    rec_out = A.record([{"door": "reuse"}])
    ok(rec_out["schema"] == A.SCHEMA and rec_out["decisions"] == [{"door": "reuse"}], "reuse.json shape")

    # 7. the Artifacts rows carry reused_from for a held reuse only
    run2 = os.path.join(TMP, "runs", "j2-20260104-000000")
    put(run2, "artifacts.json", {"schema": "artifacts/1", "rows": []})
    put(run2, "reuse.json", A.record([
        {"workflow": "W-2", "door": "reuse", "held": True, "section": "Goals", "key": "W-1", "source": {"run": SRC, "workflow": "W-1"}},
        {"workflow": "W-3", "door": "reuse", "held": False, "section": "Users", "key": "W-2", "source": {"run": SRC, "workflow": "W-2"}}]))
    ok(A.reused_from(run2) == {"W-2": {"run": SRC, "workflow": "W-1", "key": "W-1", "section": "Goals"}}, "reused_from: held only")
    print(f"artifact_lib_test: {passed} checks passed")
finally:
    shutil.rmtree(TMP, ignore_errors=True)
