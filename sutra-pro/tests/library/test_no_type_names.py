"""No output type is named in the code that must read types from data (J2 sync 5, D166, D167, D171, D172).

J2's `artifacts/types.json` (and the user's local types, and the types a capability registers) say which types exist. The library, the
two page modules that build the choices, the rehydrate module and the function-node layer take names from the data and hold none. A test
file may name types as test data; these files may not.

The scan reads the code, not the comments: a quoted type name (`"website"`, 'prd', ...) in a line that is not a comment."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "sutra_app"
NAMES = ("website", "prd", "hld", "lld", "design", "project", "business_report")
QUOTED = re.compile(r"""["'](?:%s)["']""" % "|".join(NAMES))
FILES = sorted([*ROOT.joinpath("library").rglob("*.py"), *ROOT.joinpath("engine", "fnodes").rglob("*.py"),
                ROOT / "engine" / "rehydrate.py", ROOT / "ui" / "static" / "js" / "output_pick.js",
                ROOT / "ui" / "static" / "js" / "settings_view.js"])


def code_lines(path: Path):
    in_doc = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if path.suffix == ".py":
            if text.count('"""') % 2 == 1:
                in_doc = not in_doc
                continue
            if in_doc or text.startswith("#"):
                continue
            text = text.split("  # ")[0]
        else:
            if text.startswith(("/*", "*", "//")):
                continue
            text = text.split(" // ")[0]
        yield number, text


def test_the_scan_finds_the_files_it_is_about():
    names = {p.name for p in FILES}
    assert {"templates.py", "records.py", "workflow.py", "rehydrate.py", "registry.py", "output_pick.js", "settings_view.js"} <= names


@pytest.mark.parametrize("path", FILES, ids=[str(p.relative_to(ROOT)) for p in FILES])
def test_no_type_name_is_quoted_in_the_code(path):
    found = [(n, line) for n, line in code_lines(path) if QUOTED.search(line)]
    assert found == [], f"{path.relative_to(ROOT)} names an output type: {found[:3]}"


def test_the_scan_catches_a_name():
    assert QUOTED.search('x = "website"') and QUOTED.search("y = ['prd']") and not QUOTED.search('z = "website_form"')
