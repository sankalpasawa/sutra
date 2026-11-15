"""The traceability generator (GAP-TRACE): the check on the real repository, the parsers on small fixtures, the rows on a tiny repository."""
import importlib.util
import json
import re
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_traceability", ROOT / "scripts" / "build_traceability.py")
bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bt)


def handler_count() -> int:
    """`HANDLER_COUNT` of sutra_app/engine/views.py, read as text (importing the module would import J2 into the test process)."""
    found = re.search(r"^HANDLER_COUNT = (\d+)", (ROOT / "sutra_app" / "engine" / "views.py").read_text(encoding="utf-8"), re.M)
    assert found, "HANDLER_COUNT is not where the test looks for it"
    return int(found.group(1))


# ---- the real repository ---------------------------------------------------------------------------------------------------------

def test_the_committed_traceability_file_passes_the_check_on_the_real_repository(capsys):
    assert bt.main(["--check"]) == 0
    assert "traceability check: ok" in capsys.readouterr().out
    problems, _ = bt.check(ROOT)
    assert problems == []


def test_a_fresh_run_on_the_real_repository_has_every_row_and_is_deterministic():
    first = bt.build_document(ROOT, merges={"E0": ["abc1234"]})
    second = bt.build_document(ROOT, merges={"E0": ["abc1234"]})
    assert bt.dump_json(first) == bt.dump_json(second)
    assert bt.render_markdown(first) == bt.render_markdown(second)
    assert first["counts"]["endpoints"] == 43 and first["counts"]["chips"] == 17 and first["counts"]["steps"] == 7
    assert first["counts"]["endpoints"] == handler_count()        # one row per handler of engine/views.py (J2 sync 4: 41)
    headings = bt.parse_decisions((ROOT / "docs" / "DECISIONS.md").read_text(encoding="utf-8"))
    assert [row["id"] for row in first["decisions"]] == [d["id"] for d in headings]
    assert [row["n"] for row in first["endpoints"]] == list(range(1, handler_count() + 1))
    assert [p["id"] for p in first["packages"]] == sorted((p["id"] for p in first["packages"]), key=bt.natural)
    e0 = next(p for p in first["packages"] if p["id"] == "E0")
    assert e0["status"] == "merged" and e0["merge_commits"] == ["abc1234"]
    assert next(p for p in first["packages"] if p["id"] == "E1")["status"] == "pending"


def test_every_owner_rule_of_decisions_md_has_modules_and_tests():
    doc = bt.build_document(ROOT, merges={})
    assert len(doc["owner_rules"]) == 7
    for row in doc["owner_rules"]:
        assert row["modules"] and row["tests"] and row["decisions"], row["rule"]


# ---- parsers ---------------------------------------------------------------------------------------------------------------------

DECISIONS = textwrap.dedent("""\
    # Decision log

    ## Owner rules (given, not decided here)

    | Rule | Source |
    |---|---|
    | There is ONE global org chart. | owner, 2026-11-03 |
    | Keep merging locally; never push. | owner, standing rule |

    ## D1 — Own repository
    - Sources: ENG-D1, S1-contracts-09 (S4-fnodes-14 amends it)
    - Decided: local git only.
    - Rejected: a folder in J2.
    - Diagram: none.

    ## D12 - A web app
    - Decided: one command.

    ## Not a decision
    - Decided: ignored.
""")


def test_a_decision_heading_gives_its_number_title_and_labelled_bullets():
    rows = bt.parse_decisions(DECISIONS)
    assert [(r["id"], r["n"]) for r in rows] == [("D1", 1), ("D12", 12)]
    assert rows[0]["title"] == "Own repository"
    assert rows[0]["decided"] == "local git only." and rows[0]["rejected"] == "a folder in J2." and rows[0]["diagram"] == "none."
    assert rows[0]["sources"].startswith("ENG-D1")
    assert rows[1]["title"] == "A web app" and rows[1]["rejected"] == ""
    assert "ignored" not in rows[1]["body"]


def test_owner_rules_are_the_table_rows_without_header_and_separator():
    assert bt.parse_owner_rules(DECISIONS) == [{"rule": "There is ONE global org chart.", "source": "owner, 2026-11-03"},
                                               {"rule": "Keep merging locally; never push.", "source": "owner, standing rule"}]


NOTE = textwrap.dedent("""\
    # X9 as built: a thing

    ## Built
    - D12 and D3 are cited; ORCH-D5, UI-D6 and d3.js and D3.js are not decisions. Source S1-contracts-03 and ENG-D2 too.
    - tests/engine/test_a.py and tests/ui/js/b.test.js

    ## Deviations and decisions
    - one
""")


def test_a_notes_file_gives_title_sections_decisions_tags_and_tests():
    note = bt.parse_notes(NOTE, "X9.md")
    assert note["id"] == "X9" and note["title"] == "X9 as built: a thing"
    assert note["sections"] == ["Built", "Deviations and decisions"]
    assert note["decisions"] == [3, 12]
    assert {"S1-contracts-03", "ENG-D2"} <= set(note["tags"]) and "ORCH-D5" in note["tags"]
    assert note["tests"] == ["tests/engine/test_a.py", "tests/ui/js/b.test.js"]
    assert note["lines"] == 8


def _entry(i, **kw):
    base = {"id": i, "title": f"t{i}", "owns": [f"sutra_app/{i}.py"], "depends_on": [], "section": "library"}
    base.update(kw)
    return base


def test_a_plan_entry_is_validated_and_sorted_naturally():
    plan = {"work_packages": [_entry("E10"), _entry("E2"), _entry("CN-1", depends_on=["E2"])]}
    assert [p["id"] for p in bt.parse_plan(plan)] == ["CN-1", "E2", "E10"]
    with pytest.raises(ValueError, match="lacks owns"):
        bt.parse_plan({"work_packages": [{"id": "A", "title": "t", "depends_on": [], "section": "x"}]})
    with pytest.raises(ValueError, match="twice"):
        bt.parse_plan({"work_packages": [_entry("A"), _entry("A")]})
    with pytest.raises(ValueError, match="no id"):
        bt.parse_plan({"work_packages": [{"title": "t"}]})
    with pytest.raises(ValueError, match="work_packages"):
        bt.parse_plan({})


def test_the_merge_log_keeps_every_merge_of_a_package_newest_first():
    log = "bbbbbbb|Merge wp/L7\nccccccc|Merge wp/E0\naaaaaaa|Merge wp/L7\nddddddd|Merge branch 'x'\nnot a line\n"
    assert bt.parse_merge_log(log) == {"L7": ["bbbbbbb", "aaaaaaa"], "E0": ["ccccccc"]}


def test_a_path_belongs_to_the_package_that_owns_it_exactly_by_folder_or_by_glob():
    packages = [{"id": "A", "owns": ["sutra_app/a.py", "docs/x/"]}, {"id": "B", "owns": ["tests/golden_*.json"]}]
    assert bt.owner_of("sutra_app/a.py", packages) == "A"
    assert bt.owner_of("docs/x/deep/file.md", packages) == "A"
    assert bt.owner_of("tests/golden_1.json", packages) == "B"
    assert bt.owner_of("sutra_app/b.py", packages) is None
    assert bt.owner_of("sutra_app/a.pyc", packages) is None


def test_decision_numbers_display_as_ranges():
    assert bt.ranges([5, 1, 2, 3, 3]) == "D1-D3, D5"
    assert bt.ranges([]) == ""
    assert bt.ranges([7]) == "D7"


def test_a_golden_key_belongs_to_the_longest_view_name_it_starts_with():
    names = ["artifacts", "artifacts_tree", "artifact", "library", "library_item", "state"]
    assert bt.golden_owner("artifacts_tree", names) == "artifacts_tree"
    assert bt.golden_owner("artifact_missing", names) == "artifact"
    assert bt.golden_owner("library_item", names) == "library_item"
    assert bt.golden_owner("state_since", names) == "state"
    assert bt.golden_owner("unknown", names) is None


def test_small_source_parsers_read_chips_views_routes_and_literals():
    gen = 'x = 1\nchips = [("Alpha", "a"), ("Beta", "b")]\n'
    assert bt.parse_chip_labels(gen) == ["Alpha", "Beta"] and bt.parse_chip_labels("y = 2") == []
    views = "VIEWS: dict = {fn.__name__: fn for fn in (index, state, site)}\n"
    assert bt.parse_view_names(views) == ["index", "state", "site"] and bt.parse_view_names("a = 1") == []
    assert bt.parse_j2_exact('const J2_EXACT = [\n "/api/state", "/api/runs",\n];') == ["/api/state", "/api/runs"]
    assert bt.literal_assign('ROUTES = (("/a", "a"),)\n', "ROUTES") == (("/a", "a"),)
    assert bt.literal_assign("ROUTES = make()\n", "ROUTES") is None and bt.literal_assign("x = 1\n", "ROUTES") is None


def test_features_load_from_the_real_file_with_seventeen_chips():
    features = bt.load_features(ROOT / "sutra_app" / "engine" / "features.py")
    assert sum(1 for f in features if f.kind == "chip") == 17 and sum(1 for f in features if f.kind == "step") == 8


# ---- a dead path is reported ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("rel, fragment", [
    ("sutra_app/missing.py", "file does not exist"), ("sutra_app/nodir/", "folder does not exist"),
    ("tests/none_*.py", "matches nothing"), ("../outside.py", "not a path inside"), ("/etc/hosts", "not a path inside"), ("", "empty path")])
def test_a_dead_or_unsafe_path_is_a_problem(tmp_path, rel, fragment):
    (tmp_path / "sutra_app").mkdir()
    assert fragment in bt.path_problem(tmp_path, rel)


def test_a_live_file_folder_and_glob_are_fine(tmp_path):
    (tmp_path / "a" / "sub").mkdir(parents=True)
    (tmp_path / "a" / "f.py").write_text("x")
    assert bt.path_problem(tmp_path, "a/f.py") is None and bt.path_problem(tmp_path, "a/sub/") is None
    assert bt.path_problem(tmp_path, "a/*.py") is None


# ---- --check on a fixture repository -------------------------------------------------------------------------------------------------

def _repo(tmp_path, decisions=("D1", "D2"), rows=None, **sections):
    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "notes").mkdir()
    (tmp_path / "sutra_app").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "sutra_app" / "m.py").write_text("x = 1\n")
    (tmp_path / "tests" / "test_m.py").write_text("def test_m(): pass\n")
    (tmp_path / "docs" / "notes" / "A.md").write_text("# A\n")
    (tmp_path / "docs" / "DECISIONS.md").write_text("\n".join(f"## {d} — title {d}\n- Decided: x" for d in decisions) + "\n", encoding="utf-8")
    doc = {
        "schema": bt.SCHEMA,
        "owner_rules": [{"rule": "r", "modules": ["sutra_app/m.py"], "tests": ["tests/test_m.py"]}],
        "steps": [{"step": "1 s", "modules": ["sutra_app/m.py"], "tests": ["tests/test_m.py"]}],
        "chips": [{"id": "c", "modules": ["sutra_app/m.py"], "tests": ["tests/test_m.py"]}],
        "endpoints": [{"n": 1, "name": "state", "handler": "sutra_app/m.py", "adapter": "sutra_app/m.py", "tests": ["tests/test_m.py"]}],
        "decisions": rows if rows is not None else [{"id": "D1", "packages": ["A"]}, {"id": "D2", "packages": []}],
        "packages": [{"id": "A", "status": "merged", "notes": "docs/notes/A.md", "owns": ["sutra_app/m.py"], "merge_commits": ["abc1234"]},
                     {"id": "B", "status": "pending", "notes": "docs/notes/B.md", "owns": ["sutra_app/not_yet.py"], "merge_commits": []}]}
    doc.update(sections)
    (tmp_path / bt.JSON_REL).write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path


def test_a_consistent_fixture_repository_passes_and_a_pending_package_may_own_missing_files(tmp_path):
    assert bt.check(_repo(tmp_path)) == ([], [])


def test_a_dead_module_test_or_note_in_any_row_is_reported(tmp_path):
    root = _repo(tmp_path,
                 owner_rules=[{"rule": "r", "modules": ["sutra_app/gone.py"], "tests": ["tests/test_m.py"]}],
                 steps=[{"step": "1 s", "modules": ["sutra_app/m.py"], "tests": ["tests/test_gone.py"]}],
                 chips=[{"id": "c", "modules": ["sutra_app/m.py"], "tests": ["tests/test_m.py", "tests/chip_gone.py"]}],
                 endpoints=[{"n": 3, "name": "say", "handler": "sutra_app/m.py", "adapter": "sutra_app/adapter_gone.py", "tests": []}],
                 packages=[{"id": "A", "status": "merged", "notes": "docs/notes/GONE.md", "owns": ["sutra_app/owns_gone.py"],
                            "merge_commits": ["abc1234"]}])
    problems, _ = bt.check(root)
    text = "\n".join(problems)
    for dead in ("sutra_app/gone.py", "tests/test_gone.py", "tests/chip_gone.py", "sutra_app/adapter_gone.py", "docs/notes/GONE.md",
                 "sutra_app/owns_gone.py"):
        assert dead in text, dead


def test_an_owner_rule_without_a_module_or_a_test_and_a_merged_package_without_a_commit_are_problems(tmp_path):
    root = _repo(tmp_path, owner_rules=[{"rule": "lonely", "modules": [], "tests": []}],
                 packages=[{"id": "A", "status": "merged", "notes": "docs/notes/A.md", "owns": [], "merge_commits": []}])
    text = "\n".join(bt.check(root)[0])
    assert "'lonely': no module or no test" in text and "package A: merged but no merge commit" in text


def test_a_decision_below_the_last_recorded_one_without_a_row_is_a_problem(tmp_path):
    root = _repo(tmp_path, decisions=("D1", "D2", "D3"), rows=[{"id": "D1", "packages": []}, {"id": "D3", "packages": []}])
    problems, notices = bt.check(root)
    assert problems == ["D2: has a heading in docs/DECISIONS.md but no row in docs/design/traceability.json"] and notices == []


def test_a_decision_added_after_the_file_was_made_is_only_a_notice(tmp_path):
    """Later packages add decisions; their merges must not fail until someone refreshes the file."""
    root = _repo(tmp_path, decisions=("D1", "D2", "D3", "D4"))
    problems, notices = bt.check(root)
    assert problems == [] and [n.split(":")[0] for n in notices] == ["D3", "D4"]


def test_a_row_for_a_decision_that_is_gone_and_a_row_naming_an_unknown_package_are_problems(tmp_path):
    root = _repo(tmp_path, decisions=("D1",), rows=[{"id": "D1", "packages": ["ZZ"]}, {"id": "D2", "packages": []}])
    text = "\n".join(bt.check(root)[0])
    assert "D2: has a row" in text and "decision D1: names the unknown package ZZ" in text


def test_a_file_that_is_missing_unparsable_of_another_schema_or_empty_is_refused(tmp_path):
    assert "does not exist" in bt.check(tmp_path)[0][0]
    root = _repo(tmp_path)
    target = root / bt.JSON_REL
    target.write_text("{not json", encoding="utf-8")
    assert "does not parse" in bt.check(root)[0][0]
    target.write_text(json.dumps({"schema": "other/9"}), encoding="utf-8")
    assert "schema is not traceability/1" in bt.check(root)[0][0]
    target.write_text("[]", encoding="utf-8")
    assert "schema is not" in bt.check(root)[0][0]
    other = tmp_path / "other"
    other.mkdir()
    assert "section chips is missing or empty" in bt.check(_repo(other, chips=[]))[0][0]


def test_the_command_prints_the_first_twenty_problems_and_exits_with_one(tmp_path, capsys):
    modules = [f"sutra_app/dead_{i:02d}.py" for i in range(25)]
    root = _repo(tmp_path, owner_rules=[{"rule": "r", "modules": modules, "tests": ["tests/test_m.py"]}])
    assert bt.main(["--check", "--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert out.count("problem: ") == 20 and "dead_19.py" in out and "dead_20.py" not in out and "and 5 more" in out
    assert "25 problem(s)" in out


def test_the_command_exits_zero_and_prints_notices_to_stderr(tmp_path, capsys):
    root = _repo(tmp_path, decisions=("D1", "D2", "D3"))
    assert bt.main(["--check", "--root", str(root)]) == 0
    captured = capsys.readouterr()
    assert "traceability check: ok" in captured.out and "notice: D3" in captured.err


# ---- the rows of a tiny repository ---------------------------------------------------------------------------------------------------

def _mini(tmp_path):
    def put(rel, text):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(text), encoding="utf-8")

    put("docs/build-plan.json", json.dumps({"work_packages": [
        _entry("A1", owns=["sutra_app/a.py", "docs/notes/A1.md"]), _entry("B1", owns=["sutra_app/b.py", "docs/notes/B1.md"])]}))
    put("docs/DECISIONS.md", """\
        ## Owner rules (given, not decided here)

        | Rule | Source |
        |---|---|
        | Decide autonomously; document each decision. | owner |
        | An unmapped wish. | owner |

        ## D1 — First
        - Sources: owner
        ## D2 — Second
        - Sources: owner
        ## D3 — Third
        - Status: rejected by the owner
        ## D4 — Fourth
        - Sources: S1-contracts-01
        ## D5 — Fifth supersedes D2
        - Decided: package B1 does it; this supersedes D2.
        ## D6 — Sixth
        - Sources: S2-models-09 (a note of B1 cites it)
        """)
    put("docs/notes/B1.md", "# B1\nBuilt for S2-models-09.\n")
    put("docs/notes/A1.md", "# A1\nWe did D1 here. See tests/test_a.py.\n")
    put("sutra_app/a.py", "# S1-contracts-01 is implemented here\n")
    put("sutra_app/engine/features.py", """\
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class Feature:
            id: str
            kind: str
            chip: str
            files: tuple
            flags: tuple = ()

        FEATURES = (Feature("J2.a", "step", "step", ("j2.py",)), Feature("one", "chip", "Chip One", ("j2.py", "templates/"), ("flag",)))
        """)
    put("docs/diagram/gen.py", 'chips = [("Chip One shown", "sub")]\n')
    put("sutra_app/engine/api/state.py", 'ROUTES = (("/api/state", "state"),)\n')
    put("sutra_app/engine/api/commands.py", 'ROUTES = (("/api/say", "say"),)\n')
    put("sutra_app/engine/views.py", "VIEWS = {fn.__name__: fn for fn in (index, state, site, say)}\n")
    put("tests/engine/golden/api_shapes.json", json.dumps({"get": {"live": {"state": {}, "state_since": {}, "site_v1": {}}}, "post": {"say": {}}}))
    put("sutra_app/ui/static/js/sutra_ctx.js", 'const J2_EXACT = ["/api/state"];\n')
    return tmp_path


def test_a_tiny_repository_yields_the_rows_the_parsers_found(tmp_path):
    doc = bt.build_document(_mini(tmp_path), merges={"A1": ["abc1234", "def5678"]})
    assert doc["counts"] == {"decisions": 6, "packages": 2, "endpoints": 5, "chips": 1, "steps": 7, "owner_rules": 2}
    assert doc["max_decision"] == 6
    rules = {r["rule"]: r for r in doc["owner_rules"]}
    assert rules["Decide autonomously; document each decision."]["decisions"] == ["D1", "D2", "D3", "D4", "D5", "D6"]
    assert rules["An unmapped wish."]["modules"] == [] and rules["An unmapped wish."]["tests"] == []
    assert doc["chips"] == [{"id": "one", "chip": "Chip One", "diagram_label": "Chip One shown", "modules": [
        "sutra_app/engine/j2.py", "sutra_app/engine/templates/"], "flags": ["flag"], "tests": ["tests/engine/test_engine_features.py"]}]
    by_name = {e["name"]: e for e in doc["endpoints"]}
    assert list(by_name) == ["index", "state", "site (saved)", "site (live)", "say"]
    assert (by_name["state"]["method"], by_name["state"]["path"], by_name["state"]["in_ui_list"]) == ("GET", "/api/state", True)
    assert by_name["state"]["golden_keys"] == ["state", "state_since"] and by_name["state"]["adapter"] == "sutra_app/engine/api/state.py"
    assert by_name["say"]["method"] == "POST" and by_name["say"]["golden_keys"] == ["say"] and by_name["say"]["in_ui_list"] is False
    assert by_name["site (saved)"]["path"] == "/site/{key}?run=" and by_name["site (live)"]["golden_keys"] == ["site_v1"]
    assert by_name["index"]["adapter"] == "sutra_app/ui/routes.py"
    assert [(p["id"], p["status"], p["merge_commits"]) for p in doc["packages"]] == [
        ("A1", "merged", ["abc1234", "def5678"]), ("B1", "pending", [])]


def test_a_decision_is_implemented_documented_only_or_rejected_by_what_cites_it(tmp_path):
    rows = {r["id"]: r for r in bt.build_document(_mini(tmp_path), merges={})["decisions"]}
    assert (rows["D1"]["status"], rows["D1"]["packages"]) == ("implemented", ["A1"])            # a note cites D1
    assert rows["D2"]["status"] == "documented only" and rows["D2"]["superseded_by"] == ["D5"]
    assert rows["D3"]["status"] == "rejected"
    assert (rows["D4"]["status"], rows["D4"]["packages"]) == ("implemented", ["A1"])            # its source tag is in A1's code
    assert (rows["D5"]["status"], rows["D5"]["packages"]) == ("documented only", ["B1"])        # only its own text names B1
    assert (rows["D6"]["status"], rows["D6"]["packages"]) == ("implemented", ["B1"])            # a note cites its source tag


def test_the_markdown_has_one_table_per_kind_of_row_and_pipes_in_text_are_escaped(tmp_path):
    doc = bt.build_document(_mini(tmp_path), merges={"A1": ["abc1234"]})
    doc["decisions"][0]["title"] = "a | b"
    text = bt.render_markdown(doc)
    for heading in ("## A. Owner rules", "## B. The seven draw.io steps", "## C. The 15 chips", "## D. The J2 endpoints", "## E. Decisions",
                    "## F. Work packages"):
        assert heading in text
    assert "a \\| b" in text and "| A1 |" in text and "abc1234" in text and "pending" in text
    assert "D1-D6" in text                                                                       # the rule that covers every decision
