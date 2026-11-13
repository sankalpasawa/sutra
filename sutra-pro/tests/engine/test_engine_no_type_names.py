"""The app names no output type (J2 sync 5, D165 to D168; widened by J2 sync 6, D188): types are data, so every Python file of the engine layer and
the library holds no quoted type name and no `OUTPUTS` table. Not in the list: tests, and the vendored J2 files (the 19 code modules of
`scripts/vendor_j2.py`, whose data trees `agents/`, `conditions/`, `templates/`, `artifacts/`, `seed/` hold no Python of the app).

The names are the four of J2's own types and the three that the app has met: `website`, `prd`, `hld`, `lld`, `document`, `project`, `business_report`.
Where a literal has an owner, the owner is named here with the reason, and the test fails if the owner stops needing it:

    capabilities/project.py   `project`: the capability's own type, defined once as `TYPE` (D128); everything else reads `project.TYPE`
    forms.py                  `document`: J2's form word, defined once as `DOCUMENT`, with `is_document()` (D168)
    capabilities/select.py    `project`: the id of a RULE of the selection table, not a type (`RULE_PROJECT`)

and one file of another lane that still spells a form word, listed until that lane merges (PENDING)."""
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2] / "sutra_app" / "engine"
APP = ENGINE.parent
VENDORED = frozenset(("j2.py", "j2_agent.py", "j2_agent_models.py", "j2_agent_views.py", "j2_artifact_lib.py", "j2_artifact_models.py", "j2_artifacts.py",
                      "j2_board.py", "j2_change.py", "j2_check.py", "j2_map.py", "j2_realization.py", "j2_rules.py", "j2_schema.py", "j2_send.py",
                      "j2_story.py", "j2_studio.py", "j2_template_lib.py", "j2_types.py"))
FILES = sorted(p for base in (ENGINE, APP / "library") for p in base.rglob("*.py") if not (p.parent == ENGINE and p.name in VENDORED))
NAME = re.compile(r"""["'](website|prd|hld|lld|document|project|business_report)["']""")
TABLE = re.compile(r"\bj2\.OUTPUTS\b|\bOUTPUT_NAMES\b|\bSTAGE_WORDS\b")

OWNERS = {                                               # file (relative to sutra_app/) -> {literal: how many times it may be spelled}
    "engine/capabilities/project.py": {"project": 1},     # TYPE = "project"
    "engine/forms.py": {"document": 1},                   # DOCUMENT = "document"
    "engine/capabilities/select.py": {"project": 1},      # RULE_PROJECT = "project"
}
PENDING = {                                              # lane U's file: reads the form word three times; row 6 of table 8 moves it to `forms` there
    "engine/views.py": {"document": 3},
}


def rel(path: Path) -> str:
    return path.relative_to(APP).as_posix()


def spelled(path: Path) -> dict:
    found: dict = {}
    for name in NAME.findall(path.read_text(encoding="utf-8")):
        found[name] = found.get(name, 0) + 1
    return found


@pytest.mark.parametrize("path", FILES, ids=rel)
def test_no_quoted_type_name_and_no_type_table(path):
    text = path.read_text(encoding="utf-8")
    assert not TABLE.search(text), f"{path.name} reads a table of types"
    allowed = {**PENDING, **OWNERS}.get(rel(path), {})
    for name, count in spelled(path).items():
        assert count <= allowed.get(name, 0), f"{path.name} spells the type or form name {name!r} {count} time(s); allowed {allowed.get(name, 0)}"


def test_the_list_covers_the_files_the_design_names():
    names = {p.name for p in FILES}
    assert {"views.py", "spec.py", "runlist.py", "loop.py", "settings.py", "commands.py", "select.py", "project.py", "forms.py", "rehydrate.py",
            "records.py", "templates.py", "finish.py", "registry.py"} <= names
    assert not VENDORED & {p.name for p in FILES if p.parent == ENGINE}, "the vendored modules are outside the list"


def test_every_owner_still_spells_what_it_owns_exactly_that_often():
    for file, owned in OWNERS.items():
        assert spelled(APP / file) == owned, f"{file}: an owner that no longer needs its literal must give it up (or one that needs more must say why)"


def test_the_pending_exemption_is_an_upper_bound_that_the_other_lane_removes_when_it_moves_the_word_to_forms():
    for file, owned in PENDING.items():
        found = spelled(APP / file)
        assert all(found.get(name, 0) <= count for name, count in owned.items()), f"{file} spells more than the exemption allows"
