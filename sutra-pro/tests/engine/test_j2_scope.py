"""The J2 scope guard (J2 sync 4, lane V0): every file of `prototypes/j2` is vendored, generated, a legacy copy, or excluded with a reason.

`scripts/j2_diff_of_record.py` classifies the files of the one reference (the folder `prototypes/j2` of this repository, at a commit)
against Sutra Pro as committed. The unit tests below run its classifier, its stale search, its verdict and its command line on a
small synthetic tree (a J2 extraction, a sutra-pro folder and a VENDORED.md written for them), with two stub scripts standing in for
`vendor_j2.py` and `port_j2_ui.py`. The tests at the end read the real repository: they classify the tracked files of the commit that
VENDORED.md names. Classification only; that the files are EQUAL is what the two scripts' `--check` say, run by the tool.

Nothing here reads another repository, and a wheel install or a shallow clone skips the real-repository tests cleanly."""
import hashlib
import importlib.util
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOP = REPO.parent
_spec = importlib.util.spec_from_file_location("j2_diff_of_record", REPO / "scripts" / "j2_diff_of_record.py")
tool = importlib.util.module_from_spec(_spec)
sys.modules["j2_diff_of_record"] = tool
_spec.loader.exec_module(tool)

DUMMY = "conditions/zz-filler.json"
HEADER = "# Vendored J2 engine\n\nSource: commit `{commit}`.\n\n## Patches\n| Id | What | Where |\n|---|---|---|\n| P1 | imports | a.py:1 |\n\n## Files\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class World:
    """A J2 extraction (`src`) and a sutra-pro folder (`root`) with the VENDORED.md that describes the vendored part of them."""

    def __init__(self, tmp_path: Path, commit: str = "c0ffee0" * 5 + "c0ffe"):
        self.tmp, self.commit = tmp_path, commit
        self.root, self.src = tmp_path / "sutra-pro", tmp_path / "j2src"
        self.root.mkdir()
        self.src.mkdir()
        self.rows: list[tuple[str, str, str, str, str]] = []

    def put(self, base: Path, rel: str, data) -> Path:
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path

    def j2(self, rel: str, data="j2\n") -> None:
        self.put(self.src, rel, data)

    def copy(self, rel: str, data) -> None:
        self.put(self.root, rel, data)

    def vendor(self, j2_rel: str, dest_rel: str, j2_data="j2\n", copy_data=None, patches="-", recorded_j2=None, recorded_copy=None):
        """A J2 file, the vendored copy of it and the row of VENDORED.md. By default the copy is the J2 file, the row is true."""
        j2_bytes = j2_data.encode("utf-8") if isinstance(j2_data, str) else j2_data
        copy_bytes = j2_bytes if copy_data is None else (copy_data.encode("utf-8") if isinstance(copy_data, str) else copy_data)
        self.put(self.src, j2_rel, j2_bytes)
        self.put(self.root, dest_rel, copy_bytes)
        self.rows.append((dest_rel, j2_rel, patches, recorded_j2 or sha(j2_bytes), recorded_copy or sha(copy_bytes)))

    def write_md(self, header: str | None = None) -> None:
        lines = [(header if header is not None else HEADER.format(commit=self.commit)),
                 "| Vendored path | J2 path | Patches | J2 sha256 | Vendored sha256 |", "|---|---|---|---|---|"]
        lines += [f"| `{d}` | `{j}` | {p} | `{a}` | `{b}` |" for d, j, p, a, b in self.rows]
        self.put(self.root, tool.VENDORED_MD, "\n".join(lines) + "\n")

    def ctx(self, **kw):
        if not self.rows:                 # the table must not be empty (an empty one means the format changed): one filler row
            self.vendor(DUMMY, "sutra_app/engine/" + DUMMY)
        self.write_md()
        return tool.Context.load(self.root, **kw)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def passing_world(tmp_path) -> World:
    """Every kind of file once, all decided, nothing different: what the tool should call a pass when both checks do."""
    w = World(tmp_path)
    w.vendor("j2.py", "sutra_app/engine/j2.py", "x = 1\n", copy_data="from . import y\nx = 1\n", patches="P1")
    w.vendor("j2_map.py", "sutra_app/engine/j2_map.py")
    w.vendor("agents/j2/team.md", "sutra_app/engine/agents/j2/team.md")
    w.vendor("library/a/v1/meta.json", "sutra_app/engine/seed/library/a/v1/meta.json", "{}\n")
    w.vendor("README.md", "docs/reference/j2/README.md")
    w.j2("j2_ui.html", "<html>\n")
    w.copy("sutra_app/ui/pages/j2_ui.html", "<html>\n<!-- edited -->\n")
    w.j2("vendor/d3.min.js", "d3\n")
    w.copy("sutra_app/ui/static/vendor/d3.min.js", "d3\n")
    w.j2("j2_flow_test.py", "print('flow')\n")
    w.copy("tests/engine/legacy/j2_flow_test.py", "print('flow')  # edited\n")
    w.j2("llm.py", "providers\n")
    w.j2("scenarios/budget.json", "{}\n")
    return w


def stub(path: Path, *, code=0, out="", err="", help_text="") -> Path:
    """A script that stands in for vendor_j2.py or port_j2_ui.py: records its arguments, prints, exits."""
    path.write_text(textwrap.dedent(f"""\
        import sys
        if "--help" in sys.argv:
            print({help_text!r})
            sys.exit(0)
        open({str(path) + ".argv"!r}, "w").write(" ".join(sys.argv[1:]))
        sys.stdout.write({out!r})
        sys.stderr.write({err!r})
        sys.exit({code})
        """), encoding="utf-8")
    return path


def run_cli(w: World, capsys, *extra, vendor=None, port=None, commit="abc1234"):
    vendor = vendor or stub(w.tmp / "vendor_stub.py", out="vendor_j2 --check: 3 files, ok\n")
    port = port or stub(w.tmp / "port_stub.py", out="ok: 19 anchors match\n")
    w.write_md()
    code = tool.main(["--source", str(w.src), "--commit", commit, "--root", str(w.root), "--vendor-script", str(vendor),
                      "--port-script", str(port), *extra])
    return code, capsys.readouterr()


# ---- VENDORED.md ---------------------------------------------------------------------------------------------------------------------
def test_the_files_table_is_read_and_the_patch_table_is_not():
    a, b = "a" * 64, "b" * 64
    text = HEADER.format(commit="x") + f"| `sutra_app/engine/j2.py` | `j2.py` | P1,P2 | `{a}` | `{b}` |\n| `x/y.json` | `y.json` | - | `{a}` | `{a}` |\n"
    rows = tool.parse_vendored_md(text)
    assert [(r.vendored, r.j2, r.patches, r.j2_sha, r.vendored_sha) for r in rows] == [
        ("sutra_app/engine/j2.py", "j2.py", "P1,P2", a, b), ("x/y.json", "y.json", "-", a, a)]
    assert [r.patched for r in rows] == [True, False]


def test_a_files_table_with_a_sixth_column_still_parses():
    a = "a" * 64
    assert [r.j2 for r in tool.parse_vendored_md(f"| `v` | `j` | - | `{a}` | `{a}` | a note |")] == ["j"]


def test_the_header_names_a_commit_in_full_or_by_its_first_seven_characters():
    commit = "00efb179e21cb79fae157a0679e819921ac37726"
    assert tool.names_commit(HEADER.format(commit=commit), commit)
    assert tool.names_commit(HEADER.format(commit=commit[:7]), commit)
    assert not tool.names_commit(HEADER.format(commit="9" * 40), commit)
    assert not tool.names_commit("# Vendored\n\n## Files\n" + commit, commit), "only the header above the first section counts"


def test_the_vendored_commit_is_the_first_full_id_of_the_header_that_this_repository_has():
    old, new = "1" * 40, "2" * 40
    text = f"# Vendored\nSource: {old}, taken over from {new}.\n\n## Files\n{'3' * 40}\n"
    assert tool.vendored_commit(text, lambda c: c == new) == new
    assert tool.vendored_commit(text, lambda c: False) is None
    assert tool.vendored_commit(text, lambda c: c == "3" * 40) is None, "an id below the header is not the source"


# ---- the exclusion table -----------------------------------------------------------------------------------------------------------
def test_every_exclusion_has_a_group_a_reason_and_a_place_it_is_written_down():
    for e in tool.EXCLUDED:
        assert e.pattern.strip() and e.group.strip() and e.reason.strip() and e.recorded.strip(), e.pattern
    patterns = [e.pattern for e in tool.EXCLUDED]
    assert len(patterns) == len(set(patterns)), "a pattern twice: the second one can never match"


@pytest.mark.parametrize("path, group", [
    ("docs/mocks/team-solar-mock.html", "solar mock"), ("docs/mocks/j2-artifacts-mock.html", "mocks"),
    ("docs/j2-flow.jpg", "flow picture"), ("docs/other.jpg", "doc images"), ("docs/ui-simple-start-390.png", "doc images"),
    ("docs/sudoku-comparison/x.html", "sudoku comparison"), ("docs/x.html", "design docs (HTML)"), ("docs/x.pdf", "design docs (PDF)"),
    ("docs/realization-axis.dot", "diagram picture"), ("docs/build-on-run-design.md", "build-on-run design"),
    ("scenarios/rules.md", "budget-conflict demo"), ("agents/j2/_placeholders/sutra.unused.md", "placeholders"),
    ("llm.py", "replaced by Sutra's own code"), ("j2_server.py", "replaced by Sutra's own code"),
])
def test_the_most_specific_exclusion_comes_first(path, group):
    assert tool.exclusion_for(path).group == group


def test_a_path_no_exclusion_names_has_none():
    assert tool.exclusion_for("docs/j2-handoff.md") is None
    assert tool.exclusion_for("j2_map.py") is None
    assert tool.exclusion_for("agents/j2/team.md") is None


# ---- the class of a file -----------------------------------------------------------------------------------------------------------------
def test_a_file_named_in_vendored_md_is_vendored_with_the_kind_of_its_place(world):
    for j2, dest in (("j2.py", "sutra_app/engine/j2.py"), ("agents/j2/team.md", "sutra_app/engine/agents/j2/team.md"),
                     ("conditions/prd.json", "sutra_app/engine/conditions/prd.json"),
                     ("artifacts/types.json", "sutra_app/engine/artifacts/types.json"),
                     ("templates/prd/generic.json", "sutra_app/engine/templates/prd/generic.json"),
                     ("library/index.json", "sutra_app/engine/seed/library/index.json"), ("SETUP.md", "docs/reference/j2/SETUP.md")):
        world.vendor(j2, dest)
    ctx = world.ctx()
    kinds = {e.path: e.kind for e in (tool.decide(p, ctx) for p in ("j2.py", "agents/j2/team.md", "conditions/prd.json", "artifacts/types.json",
                                                                       "templates/prd/generic.json", "library/index.json", "SETUP.md"))}
    assert kinds == {"j2.py": "code module", "agents/j2/team.md": "role file", "conditions/prd.json": "condition",
                     "artifacts/types.json": "artifact types", "templates/prd/generic.json": "generic template",
                     "library/index.json": "seed library", "SETUP.md": "reference doc"}
    assert all(tool.decide(p, ctx).cls == "vendored" for p in kinds)


def test_the_generated_page_files_are_page_files_and_the_vendored_d3_is_a_page_asset(world):
    ctx = world.ctx()
    page = {p: tool.decide(p, ctx) for p in tool.PAGE_FILES}
    assert {e.cls for e in page.values()} == {"page"}
    assert {p for p, e in page.items() if e.kind == "page"} == {"j2_ui.html", "j2_ui_render.js", "j2_graph_layout.js"}
    assert page["vendor/d3.min.js"].kind == "page asset" and page["vendor/d3.min.js"].counterpart == "sutra_app/ui/static/vendor/d3.min.js"


def test_a_test_script_is_a_legacy_copy_whether_or_not_the_copy_is_there(world):
    world.copy("tests/engine/legacy/new_test.py", "x\n")
    ctx = world.ctx()
    assert tool.decide("j2_flow_test.py", ctx).cls == "legacy", "one of the four known names"
    assert tool.decide("new_test.py", ctx).cls == "legacy", "a copy that is in the folder"
    assert tool.decide("other_test.py", ctx).cls == "undecided", "no copy, not known: nobody decided"


def test_an_exclusion_with_a_reason_excludes_and_the_reason_travels_with_the_entry(world):
    e = tool.decide("negotiate.py", world.ctx())
    assert (e.cls, e.status, e.kind) == ("excluded", "n/a", "budget-conflict demo")
    assert e.reason.strip() and e.recorded.strip() and e.pattern == "negotiate.py"


def test_an_exclusion_without_a_reason_decides_nothing(world):
    ctx = world.ctx(excluded=(tool.Exclusion("x.py", "g", "  ", "somewhere"),))
    e = tool.decide("x.py", ctx)
    assert (e.cls, e.decided) == ("undecided", False) and "no reason" in e.note


@pytest.mark.parametrize("path, kind, dest", [
    ("j2_agent_models.py", "code module", "sutra_app/engine/j2_agent_models.py"),
    ("agents/j2/backend.md", "role file", "sutra_app/engine/agents/j2/backend.md"),
    ("conditions/new.json", "condition", "sutra_app/engine/conditions/new.json"),
    ("templates/backend/generic.json", "generic template", "sutra_app/engine/templates/backend/generic.json"),
    ("library/prd/x/v1/meta.json", "seed library", "sutra_app/engine/seed/library/prd/x/v1/meta.json"),
    ("docs/agent-views-j2-proposal.md", "reference doc", "docs/reference/j2/docs/agent-views-j2-proposal.md"),
])
def test_a_new_file_of_a_vendored_kind_is_unlisted_and_says_where_it_belongs(world, path, kind, dest):
    e = tool.decide(path, world.ctx())
    assert (e.cls, e.kind, e.counterpart, e.decided) == ("unlisted", kind, dest, False)


@pytest.mark.parametrize("path", ["notes.txt", "backend/x.py", "templates/prd/other.json", "j2_new_test.py", "agents/x/y/z.md", "J2.py"])
def test_a_new_file_that_no_rule_covers_is_undecided(world, path):
    e = tool.decide(path, world.ctx())
    assert (e.cls, e.status, e.decided) == ("undecided", "n/a", False)


def test_new_html_and_images_under_docs_are_excluded_by_their_kind_and_a_new_markdown_doc_is_not(world):
    ctx = world.ctx()
    assert tool.decide("docs/new-explainer.html", ctx).cls == "excluded"
    assert tool.decide("docs/new-shot.png", ctx).cls == "excluded"
    assert tool.decide("docs/new-notes.md", ctx).cls == "unlisted"


def test_the_table_comes_before_everything_else(world):
    world.vendor("docs/x.html", "docs/reference/j2/docs/x.html")      # vendored although the exclusion table would catch it
    world.vendor("j2_flow_test.py", "docs/reference/j2/flow.py")
    ctx = world.ctx()
    assert tool.decide("docs/x.html", ctx).cls == "vendored"
    assert tool.decide("j2_flow_test.py", ctx).cls == "vendored"


# ---- the status of a file -----------------------------------------------------------------------------------------------------------------
def classify_one(w: World, rel: str, port_ok=None):
    ctx = w.ctx()
    (entry,) = tool.classify(w.src, ctx, port_ok, [rel])
    return entry


def test_an_unchanged_unpatched_copy_is_identical(world):
    world.vendor("conditions/a.json", "sutra_app/engine/conditions/a.json")
    assert classify_one(world, "conditions/a.json").status == "identical"


def test_a_patched_copy_whose_j2_file_is_the_one_it_was_built_from_is_patched(world):
    world.vendor("j2.py", "sutra_app/engine/j2.py", "x = 1\n", copy_data="from . import y\nx = 1\n", patches="P1")
    assert classify_one(world, "j2.py").status == "patched"


def test_a_j2_file_that_changed_since_the_copy_was_built_differs_patched_or_not(world):
    world.vendor("j2.py", "sutra_app/engine/j2.py", "x = 2\n", copy_data="from . import y\nx = 1\n", patches="P1",
                 recorded_j2=sha(b"x = 1\n"))
    world.vendor("conditions/a.json", "sutra_app/engine/conditions/a.json", "new\n", copy_data="old\n", recorded_j2=sha(b"old\n"))
    assert classify_one(world, "j2.py").status == "differs"
    e = classify_one(world, "conditions/a.json")
    assert e.status == "differs" and "not the one" in e.note


def test_a_copy_edited_by_hand_after_vendoring_differs(world):
    world.vendor("conditions/a.json", "sutra_app/engine/conditions/a.json", "same\n", copy_data="hand edit\n")
    assert classify_one(world, "conditions/a.json").status == "differs"
    world.rows.clear()
    world.vendor("j2.py", "sutra_app/engine/j2.py", "x = 1\n", copy_data="patched\n", patches="P1", recorded_copy=sha(b"as recorded\n"))
    e = classify_one(world, "j2.py")
    assert e.status == "differs" and "VENDORED.md hash" in e.note


def test_a_row_whose_copy_is_gone_is_missing(world):
    world.vendor("conditions/a.json", "sutra_app/engine/conditions/a.json")
    (world.root / "sutra_app/engine/conditions/a.json").unlink()
    assert classify_one(world, "conditions/a.json").status == "missing"


def test_a_new_file_of_a_vendored_kind_is_missing_until_something_is_there(world):
    world.j2("j2_new.py", "x\n")
    assert classify_one(world, "j2_new.py").status == "missing"
    world.copy("sutra_app/engine/j2_new.py", "x\n")
    assert classify_one(world, "j2_new.py").status == "identical"
    world.copy("sutra_app/engine/j2_new.py", "other\n")
    assert classify_one(world, "j2_new.py").status == "differs"


def test_the_verbatim_page_files_are_compared_by_bytes(world):
    world.j2("vendor/d3.min.js", "d3\n")
    world.copy("sutra_app/ui/static/vendor/d3.min.js", "d3\n")
    assert classify_one(world, "vendor/d3.min.js").status == "identical"
    world.copy("sutra_app/ui/static/vendor/d3.min.js", "changed\n")
    assert classify_one(world, "vendor/d3.min.js").status == "differs"


@pytest.mark.parametrize("port_ok, status", [(True, "patched"), (False, "unverified"), (None, "unverified")])
def test_a_generated_page_file_is_as_good_as_the_port_check_says(world, port_ok, status):
    world.j2("j2_ui.html", "a\nb\nc\n")
    world.copy("sutra_app/ui/pages/j2_ui.html", "a\nb\nEDIT\n")
    e = classify_one(world, "j2_ui.html", port_ok)
    assert (e.status, e.gap) == (status, 1), "one J2 line is not a line of the copy"
    assert ("port_j2_ui.py --check" in e.note) == (not port_ok)


def test_a_legacy_copy_is_edited_and_the_gap_counts_the_j2_lines_it_lacks(world):
    world.j2("j2_flow_test.py", "keep\n\nlost 1\nlost 2\nkeep\n")
    world.copy("tests/engine/legacy/j2_flow_test.py", "keep\nadded by sutra\n")
    e = classify_one(world, "j2_flow_test.py")
    assert (e.status, e.gap) == ("edited", 2)


def test_a_known_legacy_test_whose_copy_is_gone_is_missing(world):
    world.j2("change_test.py", "x\n")
    assert classify_one(world, "change_test.py").status == "missing"


def test_an_excluded_and_an_undecided_file_have_no_status_to_measure(world):
    world.j2("negotiate.py")
    world.j2("notes.txt")
    assert classify_one(world, "negotiate.py").status == "n/a"
    assert classify_one(world, "notes.txt").status == "n/a"


# ---- stale -----------------------------------------------------------------------------------------------------------------------------
def test_a_row_for_a_j2_file_the_source_no_longer_has_is_stale(world):
    world.vendor("conditions/gone.json", "sutra_app/engine/conditions/gone.json")
    stale = dict(tool.find_stale(world.ctx(), set()))
    assert "sutra_app/engine/conditions/gone.json" in stale and "no longer has" in stale["sutra_app/engine/conditions/gone.json"]
    assert tool.find_stale(world.ctx(), {"conditions/gone.json"}) == []


def test_a_file_in_a_managed_folder_that_vendored_md_does_not_name_is_stale_and_a_pycache_is_not(world):
    world.vendor("conditions/a.json", "sutra_app/engine/conditions/a.json")
    world.copy("sutra_app/engine/conditions/extra.json", "x")
    world.copy("sutra_app/engine/seed/library/__pycache__/m.pyc", "x")
    world.copy("sutra_app/engine/j2_map.py", "not a managed folder: Sutra's own file")
    stale = tool.find_stale(world.ctx(), {"conditions/a.json"})
    assert [path for path, _ in stale] == ["sutra_app/engine/conditions/extra.json"]


def test_a_legacy_copy_and_a_page_output_without_a_j2_source_are_stale(world):
    world.copy("tests/engine/legacy/old_test.py", "x")
    world.copy("sutra_app/ui/pages/j2_ui.html", "x")
    paths = {p for p, _ in tool.find_stale(world.ctx(), {DUMMY})}
    assert paths == {"tests/engine/legacy/old_test.py", "sutra_app/ui/pages/j2_ui.html"}


# ---- the verdict -------------------------------------------------------------------------------------------------------------------------
def check(outcome="ok", name="vendor_j2.py --check", output=""):
    return tool.Check(name, "cmd", 0 if outcome == "ok" else 1, output, outcome)


def test_the_verdict_is_empty_only_when_both_checks_pass_and_everything_is_decided():
    decided =[tool.Entry("a", "vendored", "k", "identical"), tool.Entry("b", "excluded", "g", "n/a", reason="r")]
    assert tool.verdict(decided, check(), check(name="port_j2_ui.py --check")) == []
    assert tool.verdict(decided, None, check()) == ["the machinery checks were not run"]
    failing = tool.verdict(decided, check("build error", output="vendor_j2: j2_artifacts.py: P1 expects its anchor 2 time(s), found 3\n"),
                           check("differences", "port_j2_ui.py --check", "differs: x\n"))
    assert len(failing) == 2 and "build error (vendor_j2: j2_artifacts.py: P1 expects" in failing[0] and "differences (differs: x)" in failing[1]


def test_an_unlisted_or_undecided_file_makes_the_verdict_fail_even_when_both_checks_pass():
    pending = [tool.Entry("j2_new.py", "unlisted", "code module", "missing"), tool.Entry("notes.txt", "undecided", "unknown", "n/a")]
    (reason,) = tool.verdict(pending, check(), check())
    assert "2 file(s) of the source are not decided: 1 of a vendored kind" in reason and "1 with no rule" in reason


# ---- the report's pieces -----------------------------------------------------------------------------------------------------------------
def test_files_are_listed_by_folder_with_the_names_of_a_folder_shared_by_two_or_more():
    assert tool.folder_groups(["j2.py", "j2_map.py", "a/b/meta.json", "a/b/model.py", "c/d.json"]) == [
        "`a/b/`: `meta.json`, `model.py`", "`c/d.json`", "`j2.py`, `j2_map.py`"]


def test_a_check_prints_its_lines_and_counts_but_does_not_repeat_a_note():
    shown = tool.check_lines(tool.Check("c", "cmd", 2, "note: names the old baseline\nvendor_j2: boom\n", "build error"))
    assert shown == ["```", "vendor_j2: boom", "(1 informational note line(s) not repeated)", "```"]
    many = tool.check_lines(tool.Check("c", "cmd", 1, "".join(f"differs: f{i}\n" for i in range(30)), "differences"), cap=5)
    assert many[0] == "```" and many[-2] == "... 25 more line(s)" and len(many) == 8


def test_the_two_folders_are_replaced_in_what_a_check_printed(tmp_path):
    src, root = tmp_path / "src", tmp_path / "root"
    text = tool.tidy(f"error: {src} is not a J2 checkout; {root}/x", src, root)
    assert text == "error: <source> is not a J2 checkout; <root>/x"


def test_outcomes_follow_the_exit_code_and_a_drift_is_a_build_error():
    assert tool.outcome_of(0, "") == "ok"
    assert tool.outcome_of(2, "vendor_j2: boom") == "build error"
    assert tool.outcome_of(1, "DRIFT: J2's j2_ui.html no longer matches the port") == "build error"
    assert tool.outcome_of(1, "differs: x") == "differences"
    assert tool.outcome_of(None, "") == "error" and tool.outcome_of(7, "") == "error"


def test_a_source_that_holds_a_dot_git_is_refused_and_a_missing_folder_is_an_error(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(tool.ToolError, match=r"holds a \.git"):
        tool.list_source(tmp_path)
    with pytest.raises(tool.ToolError, match="not a folder"):
        tool.list_source(tmp_path / "nowhere")


# ---- the command line --------------------------------------------------------------------------------------------------------------------
def test_a_complete_tree_and_two_passing_checks_pass(tmp_path, capsys):
    w = passing_world(tmp_path)
    code, out = run_cli(w, capsys, "--check")
    assert code == 0, out.out
    assert "PASS: both checks pass and every file is decided." in out.out
    assert str(tmp_path) not in out.out, "a report holds no absolute path of the machine it ran on"
    assert re.search(r"\| vendored \| 5 \| 4 \| 1 \|", out.out), "four identical, one patched"
    assert "excluded" in out.out and "budget-conflict demo" in out.out


def test_a_new_file_nobody_decided_about_fails_the_check_but_not_the_report(tmp_path, capsys):
    w = passing_world(tmp_path)
    w.j2("brand_new.txt", "?\n")
    w.j2("j2_new_module.py", "x\n")
    code, out = run_cli(w, capsys, "--check")
    assert code == 1
    assert "2 file(s) of the source are not decided: 1 of a vendored kind" in out.out and "`brand_new.txt`: no row in VENDORED.md" in out.out
    code, out = run_cli(w, capsys)
    assert code == 0 and "FAIL:" in out.out, "without --check the report is printed and the exit code is 0"


def test_a_build_that_stops_is_reported_as_that_and_fails_the_check(tmp_path, capsys):
    w = passing_world(tmp_path)
    vendor = stub(w.tmp / "v.py", code=2, err="note: vendoring x, not the baseline y\nvendor_j2: j2_artifacts.py: P1 expects its anchor 2 time(s), found 3: '    import j2_map\\n'\n")
    port = stub(w.tmp / "p.py", code=1, err="DRIFT: J2's j2_ui.html no longer matches the port:\n  E5: expected 1 match, found 0\nNo file was written.\n")
    code, out = run_cli(w, capsys, "--check", vendor=vendor, port=port)
    assert code == 1
    assert "### vendor_j2.py --check: FAILED, build error" in out.out and "### port_j2_ui.py --check: FAILED, build error" in out.out
    assert "vendor_j2: j2_artifacts.py: P1 expects its anchor 2 time(s), found 3: '    import j2_map\\n'" in out.out
    assert "E5: expected 1 match, found 0" in out.out
    assert "not the baseline" not in out.out and "1 informational note line(s) not repeated" in out.out
    assert "j2_ui.html" in out.out and "unverified" in out.out, "the page files are not called equal while the port check fails"


def test_differences_named_by_the_vendor_check_are_counted(tmp_path, capsys):
    w = passing_world(tmp_path)
    vendor = stub(w.tmp / "v.py", code=1, out="differs: sutra_app/engine/j2.py\nmissing: sutra_app/engine/seed/x.json\nvendor_j2 --check: 5 files, 2 problem(s)\n")
    code, out = run_cli(w, capsys, "--check", vendor=vendor)
    assert code == 1
    assert "The check names 1 file(s) that differ, 1 that are missing and 0 that are not in the snapshot (stale)." in out.out


def test_check_and_no_machinery_cannot_be_combined(tmp_path, capsys):
    w = passing_world(tmp_path)
    with pytest.raises(SystemExit) as stop:
        run_cli(w, capsys, "--check", "--no-machinery")
    assert stop.value.code == 2


def test_no_machinery_classifies_without_running_the_scripts(tmp_path, capsys):
    w = passing_world(tmp_path)
    vendor = stub(w.tmp / "never_run.py", code=9)
    code, out = run_cli(w, capsys, "--no-machinery", vendor=vendor)
    assert code == 0 and "vendor_j2.py --check: not run (--no-machinery)" in out.out
    assert not (w.tmp / "never_run.py.argv").exists()


def test_the_commit_flag_goes_to_the_port_check_only_when_its_help_lists_it(tmp_path, capsys):
    w = passing_world(tmp_path)
    plain = stub(w.tmp / "plain.py", help_text="usage: port [--j2 J2] [--root ROOT] [--check]")
    run_cli(w, capsys, port=plain, commit="abc1234")
    assert "--commit" not in (w.tmp / "plain.py.argv").read_text()
    newer = stub(w.tmp / "newer.py", help_text="usage: port [--j2 J2] [--commit COMMIT] [--check]")
    run_cli(w, capsys, port=newer, commit="abc1234")
    assert "--commit abc1234" in (w.tmp / "newer.py.argv").read_text()
    vendor_args = (w.tmp / "vendor_stub.py.argv").read_text()
    assert f"--source {w.src}" in vendor_args and "--commit abc1234" in vendor_args and f"--dest {w.root}" in vendor_args
    assert vendor_args.endswith("--check")


def test_a_missing_vendored_md_is_an_input_error(tmp_path, capsys):
    (tmp_path / "root").mkdir()
    (tmp_path / "src").mkdir()
    code = tool.main(["--source", str(tmp_path / "src"), "--commit", "abc", "--root", str(tmp_path / "root"), "--no-machinery"])
    assert code == 2 and "VENDORED.md is missing" in capsys.readouterr().err


def test_a_script_that_cannot_be_run_is_an_error_in_the_report_not_a_crash(tmp_path, capsys):
    w = passing_world(tmp_path)
    code, out = run_cli(w, capsys, "--check", vendor=w.tmp / "no_such_script.py")
    assert code == 1 and "### vendor_j2.py --check: FAILED" in out.out


# ---- a throwaway repository: the extraction and the default commit -------------------------------------------------------------------------
def make_monorepo(tmp_path: Path) -> Path:
    repo = tmp_path / "mono"
    for rel, data in (("prototypes/j2/j2_map.py", "x = 1\n"), ("prototypes/j2/sub/data.json", "{}\n"), ("prototypes/other/ignored.txt", "no\n"),
                      ("sutra-pro/readme.txt", "r\n")):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(data, encoding="utf-8")
    row = "| `sutra_app/engine/j2_map.py` | `j2_map.py` | - | `{0}` | `{0}` |".format(sha(b"x = 1\n"))
    (repo / "sutra-pro/sutra_app/engine").mkdir(parents=True)
    (repo / "sutra-pro/sutra_app/engine/j2_map.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "sutra-pro/sutra_app/engine/VENDORED.md").write_text(HEADER.format(commit="n/a") + row + "\n", encoding="utf-8")
    identity = ["-c", "user.name=scope test", "-c", "user.email=scope@example.invalid", "-c", "commit.gpgsign=false"]
    for args in (["init", "-q"], ["add", "-A"], [*identity, "commit", "-q", "-m", "first"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    (repo / "sutra-pro/readme.txt").write_text("changed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), *identity, "commit", "-q", "-m", "second, touches only sutra-pro"], check=True, capture_output=True)
    return repo


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@needs_git
def test_without_a_source_the_folder_is_extracted_from_the_last_commit_that_touched_it(tmp_path, capsys):
    repo = make_monorepo(tmp_path)
    first = subprocess.run(["git", "-C", str(repo), "rev-list", "--max-parents=0", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert tool.resolve_commit(repo, None) == first, "the second commit did not touch prototypes/j2"
    assert tool.resolve_commit(repo, first[:8]) == first, "a short id becomes the full one"
    assert tool.resolve_commit(repo, "not-in-this-repository") == "not-in-this-repository"
    dest = tmp_path / "out"
    dest.mkdir()
    assert tool.extract(repo, first, dest) == 2
    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == ["j2_map.py", "sub/data.json"]
    code = tool.main(["--root", str(repo / "sutra-pro"), "--no-machinery"])
    out = capsys.readouterr().out
    assert code == 0 and f"at commit `{first}`" in out and "2 files, extracted from this repository with git archive" in out
    assert "(tree `" in out


def _commit(repo: Path, message: str) -> str:
    identity = ["-c", "user.name=scope test", "-c", "user.email=scope@example.invalid", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), *identity, "commit", "-q", "-m", message], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


@needs_git
def test_the_default_label_is_the_commit_vendored_md_names_while_the_folder_is_the_one_head_has(tmp_path):
    repo = tmp_path / "mono"
    (repo / "prototypes/j2").mkdir(parents=True)
    (repo / "sutra-pro").mkdir()
    page = repo / "prototypes/j2/a.py"
    page.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, capture_output=True)
    first = _commit(repo, "the folder")
    page.write_text("x = 2\n", encoding="utf-8")
    _commit(repo, "changes the folder")
    page.write_text("x = 1\n", encoding="utf-8")
    third = _commit(repo, "puts it back: the same tree again, in a newer commit")
    named = HEADER.format(commit=first)
    assert tool.resolve_commit(repo, None) == third, "nothing names a pin: the last commit that touched the folder"
    assert tool.resolve_commit(repo, None, named) == first, "the folder is the pin's, so the pin stays the label"
    assert tool.resolve_commit(repo, None, HEADER.format(commit="9" * 40)) == third, "a commit this repository lacks is no pin"
    page.write_text("x = 3\n", encoding="utf-8")
    fourth = _commit(repo, "J2 moved on")
    assert tool.resolve_commit(repo, None, named) == fourth, "the folder is no longer the pin's: the newer commit is the label"
    assert tool.resolve_commit(repo, first[:10], named) == first, "an explicit commit wins, in full"


@needs_git
def test_extracting_a_commit_that_has_no_such_folder_is_an_error(tmp_path):
    repo = make_monorepo(tmp_path)
    (tmp_path / "out").mkdir()
    with pytest.raises(tool.ToolError, match="git archive"):
        tool.extract(repo, "no-such-revision", tmp_path / "out")


# ---- the machinery's own lists and the page table agree with the scripts they mirror ---------------------------------------------------------
def test_the_managed_folders_are_the_ones_vendor_j2_manages():
    text = (REPO / tool.VENDOR_SCRIPT).read_text(encoding="utf-8")
    block = re.search(r"^MANAGED = \(([^)]*)\)", text, re.M | re.S)
    assert block, "vendor_j2.py no longer has a MANAGED tuple: update find_stale in scripts/j2_diff_of_record.py"
    assert set(re.findall(r'"([^"]+)"', block.group(1))) == set(tool.MANAGED), "the folder lists differ: update MANAGED in scripts/j2_diff_of_record.py"


def test_the_page_table_names_what_port_j2_ui_reads_and_writes():
    text = (REPO / tool.PORT_SCRIPT).read_text(encoding="utf-8")
    for j2, (dest, how) in tool.PAGE_FILES.items():
        assert re.search(r'["\']' + re.escape(Path(j2).name) + r'["\']', text), f"port_j2_ui.py no longer reads {j2}"
        if how == "edited":
            assert dest.removeprefix("sutra_app/ui/") in text, f"port_j2_ui.py no longer writes {dest}"
    assert "static/vendor/" in text


# ---- the real repository -----------------------------------------------------------------------------------------------------------------
def _git(*args, raw=False):
    done = subprocess.run(["git", "-C", str(TOP), *args], capture_output=True)
    if done.returncode:
        return None
    return done.stdout if raw else done.stdout.decode("utf-8", "replace").strip()


@pytest.fixture(scope="module")
def pinned():
    """(commit, tracked files of its prototypes/j2, whether VENDORED.md names the commit): the commit VENDORED.md says the copy was built
    from; before that file is regenerated for the pin, the last commit that touched the folder."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    if not (TOP / tool.J2_FOLDER).is_dir():
        pytest.skip("there is no prototypes/j2 beside sutra-pro here (a wheel install, a copy, or a sparse checkout)")
    text = (REPO / tool.VENDORED_MD).read_text(encoding="utf-8")

    def has_tree(commit):
        return _git("rev-parse", "--verify", f"{commit}:{tool.J2_FOLDER}") is not None

    commit = tool.vendored_commit(text, has_tree) or _git("log", "-1", "--format=%H", "HEAD", "--", tool.J2_FOLDER)
    if not commit or not has_tree(commit):
        pytest.skip("the pinned commit is not reachable here (a shallow clone)")
    listing = _git("ls-tree", "-r", "-z", "--name-only", f"{commit}:{tool.J2_FOLDER}", raw=True)
    files = sorted(p for p in (listing or b"").decode("utf-8", "replace").split("\0") if p)
    if not files:
        pytest.skip("the pinned commit has no tracked file under prototypes/j2")
    return commit, files, tool.names_commit(text, commit)


def _settle(problem: str, commit: str, names_pin: bool) -> None:
    """A problem with the table fails once VENDORED.md was made from the commit. Until then (the table still describes another J2) the
    same finding is an expected failure that shows its list: `scripts/j2_diff_of_record.py --check` is what the integrator runs."""
    if names_pin:
        pytest.fail(problem)
    pytest.xfail(problem + f" (VENDORED.md does not name {commit[:8]} yet: scripts/vendor_j2.py has not been re-run for it)")


def test_every_tracked_file_of_prototypes_j2_is_vendored_generated_a_legacy_copy_or_excluded_with_a_reason(pinned):
    commit, files, names_pin = pinned
    ctx = tool.Context.load(REPO)
    entries = [tool.decide(path, ctx) for path in files]
    assert all(e.reason.strip() for e in entries if e.cls == "excluded")
    pending = [e for e in entries if not e.decided]
    if pending:
        listed = ", ".join(f"{e.path} ({e.cls})" for e in pending[:15])
        _settle(f"{len(pending)} of the {len(files)} tracked files of prototypes/j2 at {commit[:8]} are not decided: {listed}"
                + (" ..." if len(pending) > 15 else ""), commit, names_pin)


def test_every_row_of_vendored_md_names_a_tracked_file_of_prototypes_j2(pinned):
    commit, files, names_pin = pinned
    ctx = tool.Context.load(REPO)
    gone = sorted(row.j2 for row in ctx.rows.values() if row.j2 not in set(files))
    if gone:
        _settle(f"VENDORED.md names {len(gone)} J2 file(s) that prototypes/j2 at {commit[:8]} does not have: {', '.join(gone[:15])}", commit, names_pin)


def test_the_page_and_legacy_tables_name_tracked_files_of_prototypes_j2(pinned):
    _, files, _ = pinned
    named = set(tool.PAGE_FILES) | set(tool.LEGACY_NAMES)
    assert sorted(named - set(files)) == [], "J2 renamed or removed a file the page or legacy table names: update scripts/j2_diff_of_record.py"
