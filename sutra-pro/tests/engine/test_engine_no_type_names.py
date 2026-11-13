"""The app names no output type (J2 sync 5, D165 to D168, handoff step 5): types are data, so the application files of the engine layer hold no
quoted type name and no `OUTPUTS` table. Tests, the vendored J2 files and the one project word table of `capabilities/select.py` (kept by D165) are
not in this list."""
import re
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2] / "sutra_app" / "engine"
FILES = sorted([*(ENGINE / "capabilities").rglob("*.py"), *(ENGINE / "host").rglob("*.py"), *(ENGINE / "api").rglob("*.py"),
                ENGINE / "views.py", ENGINE / "spec.py", ENGINE / "runlist.py", ENGINE / "j2_server.py",
                ENGINE.parent / "orchestrator" / "models.py"])
NAME = re.compile(r"""["'](?:website|prd|hld|lld)["']""")
TABLE = re.compile(r"\bj2\.OUTPUTS\b|\bOUTPUT_NAMES\b|\bSTAGE_WORDS\b")


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ENGINE.parent)))
def test_no_quoted_type_name_and_no_type_table(path):
    text = path.read_text(encoding="utf-8")
    assert not NAME.search(text), f"{path.name} names a type"
    assert not TABLE.search(text), f"{path.name} reads a table of types"


def test_the_list_covers_the_files_the_design_names():
    names = {p.name for p in FILES}
    assert {"views.py", "spec.py", "runlist.py", "loop.py", "settings.py", "commands.py", "select.py", "project.py"} <= names
