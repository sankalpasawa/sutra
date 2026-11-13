"""The project output's text is data (J2 sync 5, D164): flat files of the capability, each ending in exactly one newline (J2 strips one), and
the prompts of a project run are byte-identical to sync 4 for the charter format, intake, builder, atom rules and check types. The digests
are those of the strings `capabilities/project.py` held before the move (sha256 of the text without the closing newline); a change of a file
changes its digest, so the test says so."""
import hashlib
import json

import pytest

from sutra_app.engine.capabilities import project as project_module
from sutra_app.engine.capabilities.base import OutputSpec
from sutra_app.engine.capabilities.project import CHECK_TYPES, DATA, PROJECT_BUILDER, PROJECT_INTAKE, PROJECT_PLAN, PROJECT_SECTIONS

SYNC4 = {
    "project.builder.md": "ae906809342adbcbe4189814c2a652d41e0d696ed7e06ad52aa500dec6d6c40a",
    "project.intake.md": "3596e441e7491518c7ab81038784c0088e69297a0d2477f1b07adc5e7a997d36",
    "project.charter.txt": "eedccdf82d84cdf6681af89257eae49fdfbf8306f37fc31b4a06b75ca56f449d",
    "project.atom_rules.md": "92d0669511de4fadb81f887b6745f2c9e171ba201b6f9bfcc0955104ec1c03ab",
}


@pytest.mark.parametrize("name", sorted(SYNC4))
def test_each_text_file_equals_the_string_it_replaced(name):
    raw = (DATA / name).read_bytes().decode("utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n"), "exactly one closing newline: j2_types strips one"
    assert hashlib.sha256(raw[:-1].encode()).hexdigest() == SYNC4[name]


def test_the_constants_are_the_files_read_the_way_j2_reads_them():
    assert PROJECT_BUILDER == (DATA / "project.builder.md").read_text(encoding="utf-8")[:-1]
    assert PROJECT_INTAKE == (DATA / "project.intake.md").read_text(encoding="utf-8")[:-1]


def test_the_check_types_are_sync_4s_four_with_ids_unique():
    assert CHECK_TYPES == ("facts-present", "heading-present", "section-not-empty", "ids-unique")


def test_the_conditions_file_and_the_template_are_in_the_data_folder_and_parse():
    conditions = json.loads((DATA / "project.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in conditions["conditions"]] == ["PJ1", "PJ2", "PJ3"]
    template = json.loads((DATA / "project.generic.json").read_text(encoding="utf-8"))
    assert [t["section"] for t in template["templates"]] == list(PROJECT_SECTIONS)
    assert template["artifact"] == "project"


def test_the_plan_guidance_lives_in_the_adaptation_addendum_and_names_the_sections_field():
    text = project_module.ADDENDA["adaptation"]
    assert PROJECT_PLAN in text and "`sections`" in PROJECT_PLAN
    for section in PROJECT_SECTIONS:
        assert section in text


class FakeJ2:
    @staticmethod
    def doc_atom_for(secs, ids_in):
        return ("atom", tuple(secs), dict(ids_in))


def test_the_type_entry_is_json_safe_names_its_owner_and_is_not_a_planner_choice():
    spec = project_module.project_spec(FakeJ2)
    assert isinstance(spec, OutputSpec)
    entry = spec.to_type_entry("project")
    assert json.loads(json.dumps(entry)) == entry                # no callable in it
    assert (entry["kind"], entry["form"], entry["deliverable"], entry["host"]) == ("type", "document", False, "project")
    assert entry["triggers"] == [] and entry["groups"] == [] and entry["depends_on"] == [] and entry["export"] is None
    assert entry["cost"] == {"item_parts": [{"part": "doc_section", "words": ""}]}
    assert entry["file"] == "project.md" and entry["check_types"] == list(CHECK_TYPES)
    assert [r["id"] for r in entry["rubric"]] == ["PJ-1", "PJ-2", "PJ-3", "PJ-4", "PJ-5"]
    for key in ("conditions", "builder", "intake", "charter_format", "atom_rules", "template"):
        assert entry[key].startswith(str(DATA)), key            # the capability's own files, absolute names


def test_the_extras_carry_what_data_cannot_the_flags_and_the_mocks():
    extras = project_module.project_spec(FakeJ2).extras()
    assert (extras["single"], extras["workspace"], extras["deliver"]) == (True, "edit", True)
    assert callable(extras["mock_charter"]) and callable(extras["mock_section"])
    assert extras["mock_atom"] == ("atom", PROJECT_SECTIONS, {})
