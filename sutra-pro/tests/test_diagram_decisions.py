"""The owner's standing rule: every decision of docs/DECISIONS.md is in the architecture diagram, as a pill of D-numbers on the box it
concerns or, when no single box fits, in the key at the bottom (docs/diagram/decisions.json; `anchor` null = key only). The data is checked
against the log in both directions, so a decision recorded without its key entry (D105 to D115 were: the key jumped from D104 to D116) or an
entry left behind for a decision that is gone fails here, in CI, and not when somebody counts the key.

The generator (docs/diagram/gen.py) is not run: it writes arch.html beside itself and does not write on a Windows code page. Only the data
it draws from is read, as UTF-8."""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS_MD = ROOT / "docs" / "DECISIONS.md"
DIAGRAM_JSON = ROOT / "docs" / "diagram" / "decisions.json"
HEADING = re.compile(r"^##[ \t]+D(\d+)\b", re.M)          # `## D105 — title`: the dash after the number is not part of the match
FIX = ("Add each with a short key label and an anchor (the box it concerns, or null = key only), "
       "then run docs/diagram/gen.py and look at the figure (docs/diagram/README.md).")


def in_order(ids) -> str:
    """The ids as one readable list, D2 before D10 (an id that is not D<number> goes last)."""
    return ", ".join(sorted(set(ids), key=lambda i: (int(i[1:]) if re.fullmatch(r"D\d+", i) else 10**9, i)))


def logged() -> list[str]:
    """The ids that have a `## D<number>` heading in DECISIONS.md, in file order."""
    ids = [f"D{n}" for n in HEADING.findall(DECISIONS_MD.read_text(encoding="utf-8"))]
    assert ids, "no `## D<number>` heading was found in docs/DECISIONS.md: this test cannot tell what the diagram lacks"
    return ids


def entries() -> list[dict]:
    return json.loads(DIAGRAM_JSON.read_text(encoding="utf-8"))


def drawn() -> list[str]:
    """The ids of decisions.json, in file order (the key lists them in this order)."""
    ids = [entry["id"] for entry in entries()]
    assert ids, "docs/diagram/decisions.json holds no decision"
    return ids


def well_formed(entry: dict) -> bool:
    """What gen.py reads of an entry: an id D<number>, a label, an anchor that is a box name or null."""
    label, anchor = entry.get("label"), entry.get("anchor", "")
    return (re.fullmatch(r"D\d+", str(entry.get("id"))) is not None
            and isinstance(label, str) and label.strip() != ""
            and "anchor" in entry and (anchor is None or (isinstance(anchor, str) and anchor.strip() != "")))


def test_every_decision_of_decisions_md_is_in_decisions_json():
    missing = set(logged()) - set(drawn())
    assert not missing, f"docs/diagram/decisions.json lacks {len(missing)} decision(s) that docs/DECISIONS.md has: {in_order(missing)}. {FIX}"


def test_every_id_of_decisions_json_is_a_decision_of_decisions_md():
    extra = set(drawn()) - set(logged())
    assert not extra, f"docs/diagram/decisions.json has {len(extra)} id(s) without a `## D<number>` heading in docs/DECISIONS.md: {in_order(extra)}"


def test_no_id_is_in_decisions_json_twice():
    twice = [i for i, n in Counter(drawn()).items() if n > 1]
    assert not twice, f"docs/diagram/decisions.json lists these ids more than once (the key would show each of them twice): {in_order(twice)}"


def test_every_entry_has_an_id_a_label_and_an_anchor():
    """A missing field is a KeyError in gen.py: a failure when somebody draws the figure, not here."""
    bad = [str(entry.get("id", entry)) for entry in entries() if not well_formed(entry)]
    assert not bad, f"docs/diagram/decisions.json: these entries need an id D<number>, a non-empty label and an anchor (a box name or null): {', '.join(bad)}"
