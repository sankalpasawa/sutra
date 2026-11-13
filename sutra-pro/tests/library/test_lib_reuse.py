"""The record catalogue learns J2 1adb8ecd's reuse files and keys (J2 sync 6, D186): `reuse.json`, the run template keys of
`templates.json`, the provenance keys of `meta.json`, the three new chat meta keys, the run header's `by`, `reused_from` of an
artifact row, and the `run-template/1` bundle (`RunTemplateBundle`).

The fixtures in `fixtures/reuse/` were cut from mock runs of J2 1adb8ecd with the flags on (auto-reuse, then the content door), by
J2's own flow-test helpers, with the library and runs paths replaced by plain words. Strict mode must accept every one."""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sutra_app.library import records as R
from sutra_app.library.chat import HEADER_KEYS, MessageMeta, RunHeader
from sutra_app.library.registry import REGISTRY
from sutra_app.library.templates import (
    AutoReuse, RunTemplateBundle, TemplateDecision, TemplateMeta, TemplatesFile, RUN_TEMPLATE_SCHEMA,
)
from sutra_app.library.wire import ArtifactsDoc
from sutra_app.ops import doctor

FIX = Path(__file__).parent / "fixtures" / "reuse"
SEED = doctor.seed_dir()


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def strict(name, data):
    return R.gate_record(name, data, mode="strict")


def rejected(name, data):
    with pytest.raises(R.RecordRejected) as err:
        strict(name, data)
    return [(v.path, v.message) for v in err.value.violations]


# ---- reuse.json -------------------------------------------------------------------------------------------------------

def test_reuse_json_is_in_the_catalogue_and_every_door_is_accepted():
    assert R.route_for("reuse.json").family == "artifact_reuse"
    doc = load("reuse.json")
    assert {d["door"] for d in doc["decisions"]} == {"reuse", "adapt", "unknown"}
    assert strict("reuse.json", doc).family == "artifact_reuse"


def test_a_served_section_says_it_was_held_and_refunded():
    served = next(d for d in load("reuse.json")["decisions"] if d["door"] == "reuse")
    assert served["held"] is True and served["refunded"] > 0 and served["source"]["audit"] == "pass"


def test_reuse_json_is_closed_and_checked():
    doc = load("reuse.json")
    extra = copy.deepcopy(doc)
    extra["decisions"][0]["surprise"] = 1
    assert any("surprise" in path for path, _ in rejected("reuse.json", extra))
    bad = copy.deepcopy(doc)
    bad["decisions"][0]["door"] = "maybe"
    assert rejected("reuse.json", bad)
    wrong = copy.deepcopy(doc)
    wrong["schema"] = "artifact-reuse/2"
    assert any("artifact-reuse/1" in message for _, message in rejected("reuse.json", wrong))
    nosha = copy.deepcopy(doc)
    nosha["decisions"][0]["source"]["sha"] = "abc"
    assert rejected("reuse.json", nosha)


def test_the_unknown_door_has_no_source_and_still_validates():
    unknown = next(d for d in load("reuse.json")["decisions"] if d["door"] == "unknown")
    assert unknown["source"] is None and unknown["held"] is False and "refunded" not in unknown


# ---- templates.json ---------------------------------------------------------------------------------------------------

def test_templates_json_with_a_run_template_and_auto_reuse_validates():
    doc = load("templates.auto.json")
    assert doc["run_template"]["auto"] is True and doc["auto_reuse"]["picked"] == doc["run_template"]["id"]
    assert strict("templates.json", doc).family == "template.file"
    file = TemplatesFile.model_validate(doc)
    assert file.run_template.match == doc["auto_reuse"]["match"] and len(file.auto_reuse.scores) >= 3


def test_every_decision_key_of_the_run_template_paths_is_known():
    decisions = load("templates.auto.json")["decisions"]
    keys = set().union(*(d.keys() for d in decisions))
    assert {"run_template", "from_template", "template_workflow", "adapted_from", "new_family"} <= keys
    for d in decisions:
        TemplateDecision.model_validate(d)


def test_the_router_notes_for_a_refused_adaptation_are_accepted():
    decision = copy.deepcopy(load("templates.auto.json")["decisions"][0])
    decision.update(first_refused="the adapted spec failed a rule", nearest={"name": "X", "version": 2, "similarity": 0.5},
                    nearest_refused="no common field", door="reuse")
    assert TemplateDecision.model_validate(decision).nearest["similarity"] == 0.5


def test_templates_json_without_the_new_keys_still_validates():
    doc = load("templates.auto.json")
    for key in ("run_template", "auto_reuse"):
        doc.pop(key)
    for d in doc["decisions"]:
        for key in ("run_template", "from_template", "template_workflow", "adapted_from", "new_family"):
            d.pop(key, None)
    assert strict("templates.json", doc).family == "template.file"


def test_the_auto_reuse_block_is_closed_and_a_null_pick_is_the_no_match_case():
    block = copy.deepcopy(load("templates.auto.json")["auto_reuse"])
    AutoReuse.model_validate(block)
    block.update(picked=None, match=None)
    assert AutoReuse.model_validate(block).picked is None
    with pytest.raises(ValidationError):
        AutoReuse.model_validate({**block, "extra": 1})


def test_a_mock_made_template_is_scored_with_its_reason_and_not_recorded_is_a_valid_mock():
    block = copy.deepcopy(load("templates.auto.json")["auto_reuse"])
    block["scores"][0].update(mock="not recorded", eligible=False, why_not="a mock run made it, so a live run does not start from it")
    assert AutoReuse.model_validate(block).scores[0].eligible is False


# ---- meta.json, chat, artifacts --------------------------------------------------------------------------------------

def test_a_library_version_meta_with_provenance_and_both_new_keys_validates():
    meta = load("meta.adapted.json")
    assert meta["renamed_from"] and meta["adapted_from"] and meta["made_by"]["date"] and meta["business"]["name"]
    parsed = TemplateMeta.model_validate(meta)
    assert parsed.renamed_from == meta["renamed_from"] and parsed.adapted_from == meta["adapted_from"]
    assert parsed.to_json()["schema"] == "template-library/1"


def test_a_run_copy_of_a_meta_validates_through_the_catalogue():
    meta = load("meta.adapted.json")
    rel = "templates/lld/file-structure/flow-pilates-studio-file-structure@v1/meta.json"
    assert strict(rel, meta).family == "template.meta"


def test_the_chat_lines_of_a_reuse_run_validate_and_the_header_is_a_run_header():
    lines = [json.loads(line) for line in (FIX / "chat.jsonl").read_text(encoding="utf-8").splitlines()]
    assert strict("chat.jsonl", lines[0]).family == "run_header"
    kinds = set()
    for line in lines[1:]:
        assert strict("chat.jsonl", line).family == "run_message"
        kinds |= {k for k in ("humans_only", "run_template", "content_door") if k in line}
    assert kinds == {"humans_only", "run_template", "content_door"}
    assert set(MessageMeta.model_fields) >= kinds


def test_the_run_header_is_closed_and_its_author_is_a_name_never_a_path():
    head = json.loads((FIX / "chat.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert set(head) == set(HEADER_KEYS) and head["by"] == "sutra-pro"
    assert RunHeader.model_validate(head).by == "sutra-pro"
    for by in ("/home/someone", "C:\\Users\\someone", "a/b", "", "x" * 81):
        assert rejected("chat.jsonl", {**head, "by": by}), by
    older = {k: v for k, v in head.items() if k != "by"}
    assert strict("chat.jsonl", older).family == "run_header"          # a run of an older J2 has no author
    assert rejected("chat.jsonl", {**head, "surprise": 1})
    assert rejected("chat.jsonl", {k: v for k, v in head.items() if k != "run"})


def test_an_artifact_row_may_say_which_sections_were_served_from_an_earlier_run():
    row = {"name": "Product requirements", "type": "prd", "kind": "type", "form": "document", "file": "prd.md", "deliverable": True,
           "workflows": ["W-1"], "depends_on": [], "version": 2,
           "reused_from": [{"workflow": "W-1", "section": "Problem", "run": "j2-20261113-230804", "source_workflow": "W-1", "key": "W-1"}]}
    doc = {"schema": "artifacts/1", "rows": [row]}
    assert strict("artifacts.json", doc).family == "artifacts"
    without = {"schema": "artifacts/1", "rows": [{k: v for k, v in row.items() if k != "reused_from"}]}
    assert ArtifactsDoc.model_validate(without).rows[0].reused_from is None
    assert rejected("artifacts.json", {"schema": "artifacts/1", "rows": [{**row, "reused_from": [{"workflow": "W-1", "x": 1}]}]})


# ---- the run-template bundle -----------------------------------------------------------------------------------------

def workflow(n, stage="prd", depends=(), covers=()):
    return {"key": f"W-{n}", "name": f"Write part {n}", "stage": stage, "artifact": stage, "section": f"Part {n}",
            "section_template": f"Part {n} template@1", "section_template_kind": "specialised", "depends_on": list(depends),
            "covers": list(covers), "made_from": f"W-{n}", "fix": False}


def bundle(**over):
    doc = {"schema": RUN_TEMPLATE_SCHEMA, "id": "acme-docs", "name": "Acme docs", "description": "", "business_type": "shop",
           "made_from_run": "j2-20261103-100000", "mock": True, "stages": ["prd", "hld"],
           "workflows": [workflow(1), workflow(2, "prd", ["W-1"]), workflow(3, "hld", ["W-1", "W-2"])],
           "facts_slots": ["business name"], "outputs": {}, "made_by": {"run": "j2-20261103-100000"}, "used_by": [], "created": "2026-11-03T10:00:00"}
    doc.update(over)
    return doc


def test_a_run_template_bundle_validates_and_writes_back_as_j2_wrote_it():
    doc = bundle()
    parsed = RunTemplateBundle.model_validate(doc)
    assert parsed.to_json() == doc and REGISTRY.is_payload("run_template.bundle") and REGISTRY.kinds("run_template.bundle", 1) == {"run_template.bundle": RunTemplateBundle}


@pytest.mark.parametrize("change, why", [
    ({"schema": "run-template/2"}, "schema must be"),
    ({"workflows": [workflow(1), workflow(3, "prd")], "stages": ["prd"]}, "keys must run W-1, W-2"),
    ({"workflows": [workflow(1, depends=["W-2"]), workflow(2)], "stages": ["prd"]}, "names no earlier workflow"),
    ({"workflows": [workflow(1), workflow(2, "lld")]}, "is not one of the template's stages"),
    ({"workflows": [workflow(1), workflow(2, "hld"), workflow(3, "prd")], "stages": ["prd", "hld"]}, "grouped by stage"),
    ({"workflows": [{**workflow(1), "covers": ["The <studio name> is named"]}]}, "not listed in facts_slots"),
    ({"outputs": {"website": {"files": ["a.html"]}}}, "must name a stage"),
    ({"outputs": {"prd": {"files": ["../a.html"]}}}, "must name a stage"),
    ({"mock": "maybe"}, ""),
    ({"surprise": 1}, ""),
    ({"id": "Not A Slug"}, ""),
])
def test_a_run_template_bundle_is_checked_as_j2_checks_it(change, why):
    with pytest.raises(ValidationError) as err:
        RunTemplateBundle.model_validate(bundle(**change))
    assert why in str(err.value)


def test_the_id_slots_are_never_facts_and_a_not_recorded_template_is_valid():
    doc = bundle(mock="not recorded", business_type="not recorded")
    doc["workflows"][0]["covers"] = ["Requirements (<requirement ids>) are numbered"]
    assert RunTemplateBundle.model_validate(doc).mock == "not recorded"


def seed_bundles():
    return sorted((SEED / "run-templates").glob("*/template.json"))


@pytest.mark.skipif(not (SEED / "run-templates").is_dir(), reason="the vendored seed gains run templates when lane V merges")
def test_every_run_template_of_the_seed_validates_against_the_bundle():
    paths = seed_bundles()
    assert len(paths) == 4
    index = json.loads((SEED / "index.json").read_text(encoding="utf-8"))
    assert sorted(r["id"] for r in index["run_templates"]) == sorted(p.parent.name for p in paths)
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        parsed = RunTemplateBundle.model_validate(data)
        assert parsed.id == path.parent.name and parsed.to_json() == data, path
        assert (path.parent / "schema.json").is_file()
