"""The architecture diagram says what the design says (S4-fnodes section 12, S1-contracts-17): `docs/diagram/gen.py` holds the exact
strings, and the words they replaced are gone. The generator is read as text; it is never run (it writes a file next to itself)."""
import ast
import re
from pathlib import Path

import pytest

GEN = Path(__file__).resolve().parents[2] / "docs" / "diagram" / "gen.py"
TEXT = GEN.read_text(encoding="utf-8")

LIBRARY_LINES = [
    "FunctionNode (base), children <X>Node:", "Identity · Adaptation · Priority", "Coordination · Audit",
    "Atom (base): goal, constraints,", "context, work, verify, state", "AtomView: J2 atom/1 (for builders)",
    "Departments · Goal · Evaluation", "Org chart · Chart change", "Also base: Workflow · Step · Template",
    "Artifact models + rules as data", "closed models, checked at every write,", "including every org chart change",
]


def string_literals() -> set[str]:
    """Every string constant of gen.py (f-strings included, as their literal parts)."""
    return {node.value for node in ast.walk(ast.parse(TEXT)) if isinstance(node, ast.Constant) and isinstance(node.value, str)}


def library_box() -> tuple[list[str], str]:
    found = re.search(r'"Interface library \(Python models\)", (\[.*?\]), (lh=[0-9.]+, ly=[0-9]+)\)', TEXT, re.S)
    assert found, "the Interface library box is not where the contract looks for it"
    return ast.literal_eval(found.group(1)), found.group(2)


def test_the_interface_library_box_has_the_twelve_lines_in_order():
    lines, spacing = library_box()
    assert lines == LIBRARY_LINES
    assert spacing == "lh=15.5, ly=41"


@pytest.mark.parametrize("line", [
    "1 turn = 1 atom", "bad goal or check:", "logged as refused", "every call has an atom id", "one row per call, by atom",
])
def test_the_new_strip_and_ledger_wording_is_drawn(line):
    assert any(line in literal for literal in string_literals()), line


def test_the_refuse_cell_and_the_two_unchanged_cells_are_still_there():
    assert '("exit: refuse", 118, ["bad goal or check:", "logged as refused"], True)' in TEXT
    for unchanged in ('"goal, constraints,", "context, check first"', '"AI call, code step,", "or a question to you"',
                      '"pass: card + log row", "fail: retry, then recover"', '"reason required;", "no check, log row"'):
        assert unchanged in TEXT, unchanged


def test_the_aria_label_says_turn_not_step():
    assert "every turn of a node is one work atom" in TEXT
    assert "every step of a node is one work atom" not in TEXT


def test_the_codex_boxes_say_login_never_an_api_key_and_the_cli_box_says_signed_in_via_sutra():
    codex = "your ChatGPT login, never an API key"
    cli = "on this Mac · signed in via Sutra"
    assert codex in string_literals() and cli in string_literals()
    assert (len(codex), len(cli)) == (36, 33)                                       # S1-contracts-17: they fit boxes of about 41
    assert "ChatGPT login or API key in the keychain" not in TEXT
    assert "installed and signed in through Sutra" not in TEXT


def test_the_claude_boxes_stay():
    assert "your subscription login, never an API key" in TEXT
    assert '"signed in on this Mac"' in TEXT


def test_the_old_function_node_wording_is_gone():
    for old in ("AgentNode", "WorkAtom", "BuilderAtom", "1 step = 1 atom"):
        assert old not in TEXT, old
