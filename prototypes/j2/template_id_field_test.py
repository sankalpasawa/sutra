"""Offline checks that a template and the check of a reply agree on a field the template added inside one of the
generic template's objects: python template_id_field_test.py

From live run j2-20261117-154941 (Clear Counsel, 17 Nov 2026): the Success metrics template J2 had just created
gave each metric an id. The template's own class required the id; the second check, the generic Success metrics
model, has a closed metric object with no id and refused it ("success_metrics.0.id: Extra inputs are not
permitted"). No reply could pass, eight times.
(1) a freshly created template (the spec that run stored, created again here) validates a reply that uses the id,
    and the data keeps it;
(2) the same template read back from the library, and an existing library template given a new version with an id,
    do too;
(3) the check is not looser: a reply without the id, with a key the template does not have, or without what the
    generic requires is still refused;
(4) the schema sent to the model and the check agree: a reply that follows schema.json's required lists passes;
(5) every template of the committed library still validates what its generic part is, and generic_part leaves a
    section with nothing added as it is.
No AI calls. Nothing written outside a temp folder.
"""
import copy
import json
import os
import shutil
import sys
import tempfile

import j2_flow_test as t          # noqa: F401  sets STUDIO_MOCK and temp runs and library folders
import j2_artifact_models as AM    # noqa: E402
import j2_template_lib as L        # noqa: E402

passed = 0


def ok(cond, label):
    global passed
    if not cond:
        sys.exit(f"FAIL: {label}")
    passed += 1


F = lambda name, typ="string", required=True, description="": {"name": name, "type": typ, "required": required,
                                                              "description": description, "enum": None, "nullable": False}
# the spec run j2-20261117-154941 stored (templates/prd/success-metrics/clear-counsel-prd-success-metrics@v1/spec.json)
SPEC = {"name": "Clear Counsel PRD Success metrics", "artifact": "prd", "section": "Success metrics", "kind": "specialised",
        "description": "Success metrics for the Clear Counsel client intake form: no numeric target.",
        "fields": [F("success_metrics", "list[SuccessMetric]", True, "one metric per goal; M1 names G1"),
                   F("assumptions", "list[string]", False),
                   F("out_of_scope", "list[string]", True, "what this document does not cover")],
        "objects": [{"name": "SuccessMetric", "fields": [
            F("id", "string", True, "the metric id, e.g. M1"), F("goal", "string", True, "the goal id this metric measures"),
            F("metric", "string", True, "what is measured"), F("target", "string", False, "the state to reach"),
            F("window", "string", False, "the measurement window")]}],
        "rules": [], "extends": L.generic_ref("prd", "Success metrics"),
        "made_by": {"run": "test", "workflow": "W-4", "atom": "W-4.a1", "agent": "template generator (test)"},
        "context": {"business_type": "law firm", "facts_used": ["Clear Counsel"], "fingerprint": "f" * 64}}
# the reply the live run's builder sent (call 26)
REPLY = {"success_metrics": [{"id": "M1", "goal": "G1", "metric": "A prospective client can fill in the four fields and send the intake",
                              "target": "there is no numeric target", "window": "measurement window not set"}],
         "assumptions": [], "out_of_scope": ["An HLD", "An LLD", "A website"]}

tmp = tempfile.mkdtemp(prefix="j2-template-id-")
keep = os.environ.get("J2_LIBRARY_DIR")
here = os.path.dirname(os.path.abspath(__file__))
try:
    lib = os.path.join(tmp, "lib")
    shutil.copytree(os.path.join(here, "library"), lib)
    os.environ["J2_LIBRARY_DIR"] = lib
    gen = L.generic("prd", "Success metrics")
    gobj = next(o for o in gen.objects if o.name == "SuccessMetric")
    ok("id" not in {f.name for f in gobj.fields}, "the generic Success metrics template's metric has no id (the case of the live run)")
    ok(not L.refusal(SPEC), f"the spec is one the library accepts: {L.refusal(SPEC)}")

    # ---- (1) a freshly created template
    fresh, version, made = L.store(L.SpecialisedTemplate.model_validate(SPEC))
    ok(made and version == 1, f"the template is created: v{version}")
    got, errs = L.validate(fresh, REPLY)
    ok(not errs, f"a reply that uses the id the template lists is valid: {errs}")
    ok(got and got["success_metrics"][0]["id"] == "M1" and got["out_of_scope"] == REPLY["out_of_scope"], "and the data keeps the id and the added field")

    # ---- (2) the same template as the library holds it, and an existing template with an id added
    stored = L.get(f"{SPEC['name']}@1", "prd", "Success metrics")
    ok(stored is not None and stored.sha == fresh.sha, "the template is read back from the library")
    ok(L.validate(stored, REPLY) == (got, []), "read back from the library it validates the same reply")
    old_row = next(e for e in L.index()["templates"] if e["artifact"] == "prd" and e["section"] == "Success metrics"
                   and e["kind"] == "specialised" and e["name"] != SPEC["name"])
    old = L.get(f"{old_row['name']}@{old_row['versions'][-1]['version']}", "prd", "Success metrics")
    ospec = old.model_dump(exclude={"used_by", "version", "sha"})
    oobj = next(o for o in ospec["objects"] if o["name"] == "SuccessMetric")
    ok("id" not in {f["name"] for f in oobj["fields"]}, f"an existing library template without an id: {old.name} v{old.version}")
    oobj["fields"].insert(0, F("id", "string", True, "the metric id"))
    newer, nv, nmade = L.store(L.SpecialisedTemplate.model_validate({**ospec, "used_by": []}))
    ok(nmade and nv > old.version and newer.name == old.name, f"it gets a new version with the id: v{nv}")
    sample = {f.name: ([] if f.type.startswith("list[") else "x") for f in newer.fields if f.required}
    sample["success_metrics"] = [{"id": "M1", "goal": "G1", "metric": "bookings sent", "target": "none set", "window": "measurement window not set"}]
    g2, e2 = L.validate(L.get(f"{newer.name}@{nv}", "prd", "Success metrics"), sample)
    ok(not e2 and g2["success_metrics"][0]["id"] == "M1", f"the existing template's new version validates a reply with the id: {e2}")
    ok(not L.validate(old, {**sample, "success_metrics": [{k: v for k, v in sample["success_metrics"][0].items() if k != "id"}]})[1],
       "and its earlier version, which has no id, validates a reply without one, as before")

    # ---- (3) the check is not looser
    no_id = {**REPLY, "success_metrics": [{k: v for k, v in REPLY["success_metrics"][0].items() if k != "id"}]}
    ok(L.validate(fresh, no_id)[1] == ["success_metrics.0.id: Field required"], f"a reply without the id is refused: {L.validate(fresh, no_id)[1]}")
    extra = copy.deepcopy(REPLY)
    extra["success_metrics"][0]["owner"] = "the firm"
    ok(any("success_metrics.0.owner" in e and "Extra inputs" in e for e in L.validate(fresh, extra)[1]), "a key the template does not have is refused inside the object")
    ok(any(e.startswith("notes") and "Extra inputs" in e for e in L.validate(fresh, {**REPLY, "notes": "x"})[1]), "and at the top")
    ok(any("id" in e and "Extra inputs" in e for e in L.validate(old, sample)[1]), "a template without an id still refuses one")
    no_goal = copy.deepcopy(REPLY)
    del no_goal["success_metrics"][0]["goal"]
    ok(L.validate(fresh, no_goal)[1] == ["success_metrics.0.goal: Field required"], "what the generic requires of a metric is still required")
    gmodel = AM.section_models("prd")["Success metrics"]
    ok(AM.validate(gmodel, AM.normalise(gmodel, {"success_metrics": REPLY["success_metrics"]}))[1],
       "the generic model itself still refuses the id: it is closed, and was not changed")
    ok(not AM.validate(gmodel, AM.normalise(gmodel, L.generic_part(gen, REPLY)))[1], "it is given the generic's part of the data, which it accepts")
    ok(L.generic_part(gen, REPLY) == {"success_metrics": [{k: v for k, v in REPLY["success_metrics"][0].items() if k != "id"}], "assumptions": []},
       f"the generic's part: the generic's fields, the metric without the id: {L.generic_part(gen, REPLY)}")

    # ---- (4) the schema sent and the check agree
    schema = L.transport(fresh)
    metric = schema["definitions"]["SuccessMetric"]
    ok("id" in metric["properties"] and "id" in metric["required"] and metric["additionalProperties"] is False,
       "schema.json (what --json-schema is given for the section) lists the id as required in a closed object")
    least = {k: REPLY[k] for k in schema["required"]}
    least["success_metrics"] = [{k: REPLY["success_metrics"][0][k] for k in metric["required"]}]
    least["out_of_scope"] = REPLY["out_of_scope"]      # required by the template's class (the transport leaves it to the reply)
    ok(not L.validate(fresh, least)[1], f"a reply with what the schema requires passes the check: {L.validate(fresh, least)[1]}")

    # ---- (5) the committed library: nothing else changes
    n = 0
    for e in L.index()["templates"]:
        g = L.generic(e["artifact"], e["section"])
        gm = AM.section_models(e["artifact"]).get(e["section"])
        if e.get("kind") != "specialised" or g is None or gm is None or e["name"] in (SPEC["name"], old.name):
            continue
        gnames = {(f.alias or k) for k, f in gm.model_fields.items()}
        gobjs = {o.name: {f.name for f in o.fields} for o in g.objects}
        for v in e["versions"]:
            tpl = L.get(f"{e['name']}@{v['version']}", e["artifact"], e["section"])
            added = {o.name: {f.name for f in o.fields} - gobjs[o.name] for o in tpl.objects if o.name in gobjs}
            ok(not any(added.values()), f"{e['name']} v{v['version']} adds no field inside a generic object, so its check is what it was: {added}")
            n += 1
    whole = {"success_metrics": [{"goal": "G1", "metric": "m", "target": "t", "window": "w"}], "assumptions": ["a"]}
    ok(L.generic_part(gen, whole) == whole, "a section with nothing added is given to the generic model whole")
    print(f"template_id_field_test: {passed} checks passed ({n} stored template versions looked at; "
          f"{old.name} v{nv} made with an id)")
finally:
    if keep is None:
        os.environ.pop("J2_LIBRARY_DIR", None)
    else:
        os.environ["J2_LIBRARY_DIR"] = keep
    shutil.rmtree(tmp, ignore_errors=True)
