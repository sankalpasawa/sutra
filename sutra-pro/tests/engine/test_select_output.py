"""The engine chooses the output itself (work package WP4, engine design 2.4, D129): a pure rule table in `capabilities/select.py`, decided
once by the host before J2 starts. No model call, so the table is tested as a table of briefs. Since D253 no word of the brief decides:
the owner's choice, a follow-up's own output and a working folder are the only rules, and everything else goes to J2's planner."""
import inspect
from pathlib import Path

import pytest

from sutra_app.engine import capabilities
from sutra_app.engine.capabilities import select
from sutra_app.engine.capabilities.select import RULES, chat_line, choose_output

# (brief, a working folder is set, the output of the run this continues, the owner's choice) -> (output, rule)
# No default type, no deliverable phrases (D165) and no project words (D253): a brief with no folder and no earlier run is left to J2's planner
# (`None`, rule `planner`). A type name here is test data: the rules read the owner's choice and the earlier run's type as they are.
TABLE = [
    # the owner's own sentences: the words "repo", "git", "folder" decide nothing; the folder does
    ("check the details of the app and update the J2 prototype in the repo", True, None, "auto", "project", "folder"),
    ("check the details of the app and update the J2 prototype in the repo", False, None, "auto", None, "planner"),
    ("check the details of the app and update the J2 prototype", True, None, "auto", "project", "folder"),
    ("build a florist site", False, None, "auto", None, "planner"),
    ("build a florist site", True, None, "auto", "project", "folder"),          # the folder rule is all that claims a brief
    ("update the PRD in the repo", True, None, "auto", "project", "folder"),
    ("update the PRD in the repo", False, None, "auto", None, "planner"),
    # named documents with no folder: the planner decides which types they are
    ("Write a PRD for QuickQueue, a mobile app for clinics", False, None, "auto", None, "planner"),
    ("draft the HLD and the LLD for a bakery site", False, None, "auto", None, "planner"),
    ("Create design docs for a yoga studio website", False, None, "auto", None, "planner"),
    # the start page's own examples, with and without a folder
    ("A website for my cafe", False, None, "auto", None, "planner"),
    ("A website for Petal & Stem, a florist in Jaipur: bouquets, same-day delivery", True, None, "auto", "project", "folder"),
    # nothing about a project and no folder: no type, J2's planner chooses
    ("a cafe called Brew Lab with a menu and opening hours", False, None, "auto", None, "planner"),
    ("hello", False, None, "auto", None, "planner"),
    ("", False, None, "auto", None, "planner"),
    # a folder is set and the request is not a make-a-thing request
    ("look at the app and tell me what is missing", True, None, "auto", "project", "folder"),
    ("update the J2 prototype", True, None, "auto", "project", "folder"),
    # the former project words, each on its own, with no folder: the planner (D253). The brief that broke it is the last one.
    ("fix the bug in checkout", False, None, "auto", None, "planner"),
    ("refactor the login module", False, None, "auto", None, "planner"),
    ("what changed in the last commit?", False, None, "auto", None, "planner"),
    ("open a pull request for the rename", False, None, "auto", None, "planner"),
    ("read CLAUDE.md and follow it", False, None, "auto", None, "planner"),
    ("summarise the codebase", False, None, "auto", None, "planner"),
    ("update the Source of truth", False, None, "auto", None, "planner"),
    ("GIT status please", False, None, "auto", None, "planner"),
    ("Build Pulse, an agent that watches six mailboxes; the list above is the source of truth for this pilot", False, None, "auto", None, "planner"),
    # a follow-up keeps its output, whatever its words
    ("make the header blue", False, "website", "auto", "website", "followup"),
    ("fix the bug in the contact form", True, "website", "auto", "website", "followup"),
    ("update the J2 prototype in the repo", True, "website", "auto", "website", "followup"),   # a repository word no longer leaves a website follow-up: the owner picks Project work for that
    ("look at the folder and the git log", False, "website", "auto", "website", "followup"),
    ("add a section about pricing", True, "prd", "auto", "prd", "followup"),
    ("also check the tests", True, "project", "auto", "project", "followup"),
    ("also check the tests", False, "project", "auto", "project", "followup"),
    # the owner's choice beats everything
    ("update the PRD in the repo", True, None, "website", "website", "owner"),
    ("build a florist site", True, None, "project", "project", "owner"),
    ("hello", False, "website", "prd", "prd", "owner"),
    ("hello", False, None, "lld", "lld", "owner"),
]


@pytest.mark.parametrize("brief,folder,seed,choice,output,rule", TABLE, ids=[f"{i}:{r[0][:34]}" for i, r in enumerate(TABLE)])
def test_the_table(brief, folder, seed, choice, output, rule):
    got = choose_output(brief, folder, seed, choice)
    assert (got.output, got.rule) == (output, rule), got
    assert got.rule in RULES and got.reason.strip()


@pytest.mark.parametrize("word", ["repository", "repo", "repos", "codebase", "code base", "source code", "git", "branch", "commit", "commits",
                                  "pull request", "CLAUDE.md", "AGENTS.md", "the folder", "my folder", "working folder", "refactor",
                                  "refactoring", "bug", "bugs", "the app's code", "source"])
def test_no_word_of_the_brief_picks_project_work(word):
    """D253: the words that once pinned project work decide nothing; with no folder and no earlier run the planner chooses."""
    got = choose_output(f"please look at the {word} now", False)
    assert (got.output, got.rule) == (None, "planner"), word


def test_the_brief_is_not_read_and_the_word_table_is_gone():
    body = inspect.getsource(select.choose_output).split('"""')[2]
    assert "brief" not in body, "the body of choose_output reads no word of the brief (D253)"
    assert not hasattr(select, "load_words") and not hasattr(select, "STRONG_PROJECT_WORDS") and not hasattr(select, "WEAK_REASONS")
    assert not (Path(select.__file__).with_name("data") / "project.words.json").exists(), "the word file is gone"


def test_the_reason_says_what_decided():
    assert choose_output("update the repo", True).reason == "a working folder is set and the request is about it"
    assert choose_output("fix the bug", False, "project").reason == "this continues an earlier project run"
    assert choose_output("anything", False, None, "project").reason == "you chose it"
    assert choose_output("anything", False).reason == "the team's planner chooses"


def test_the_table_is_pure_and_the_same_every_time():
    args = ("check the details of the app and update the J2 prototype in the repo", True, None, "auto")
    assert choose_output(*args) == choose_output(*args)


def test_a_missing_brief_and_missing_seed_are_not_errors():
    assert choose_output(None, False).output is None          # type: ignore[arg-type]
    assert choose_output("x", False, "").rule == "planner"


def test_no_rule_names_a_default_type_a_deliverable_phrase_or_a_project_word():
    assert RULES == ("owner", "followup", "folder", "planner")
    assert not hasattr(select, "_DELIVER") and "website" not in inspect.getsource(select.choose_output)


# ---- the chat line: only for project work ------------------------------------------------------------------------------
def test_a_selection_that_is_not_project_work_posts_nothing_so_existing_runs_keep_their_events():
    for brief in ("build a florist site", "hello", "A website for my cafe", "update the PRD in the repo"):
        assert chat_line(choose_output(brief, False), False) is None


def test_a_project_selection_says_so_in_one_line_with_the_reason_and_the_way_out():
    line = chat_line(choose_output("update the PRD in the repo", True), True)
    assert line == ("Working on this as project work in your folder (a working folder is set and the request is about it; choose another kind "
                    "of result in the start page if that is wrong).")


def test_project_work_with_no_folder_says_where_to_choose_one():
    line = chat_line(choose_output("also check the tests", False, "project"), False)
    assert "no working folder is set" in line and "Working folder" in line and "earlier project run" in line


def test_an_explicit_choice_of_project_is_acknowledged_without_a_guess():
    assert chat_line(choose_output("anything", True, None, "project"), True) == (
        "Working on this as project work (you chose it in the start page or the settings).")


# ---- the registry's vote ---------------------------------------------------------------------------------------------------
def ctx(output="auto", has_folder=False, seed=None):
    from types import SimpleNamespace

    from sutra_app.engine.spec import EngineSettings
    return capabilities.EngineContext(task=SimpleNamespace(), settings=EngineSettings(output=output), paths=SimpleNamespace(),
                                      data_dir=None, has_folder=has_folder, seed_output=seed)


def test_the_registry_asks_the_capabilities_and_the_project_capability_votes():
    got = capabilities.select_output("update the PRD in the repo", ctx(has_folder=True))
    assert (got.output, got.rule) == ("project", "folder")
    got = capabilities.select_output("update the PRD in the repo", ctx())
    assert (got.output, got.rule) == (None, "planner")
    got = capabilities.select_output("build a florist site", ctx())
    assert (got.output, got.rule) == (None, "planner")


def test_the_registry_reads_the_owners_choice_from_the_settings_it_is_given():
    assert capabilities.select_output("update the PRD in the repo", ctx(output="prd")).output == "prd"


def test_with_no_capability_voting_the_teams_planner_chooses():
    got = capabilities.select_output("x", ctx(), capabilities=[])
    assert (got.output, got.rule, got.reason) == (None, "planner", "the team's planner chooses")


def test_output_names_are_checked_by_shape_in_the_settings_and_the_tasks_and_there_is_no_closed_list():
    from sutra_app.engine import spec
    from sutra_app.engine.spec import EngineSettings
    from sutra_app.orchestrator.models import TaskSettings
    assert not hasattr(spec, "OUTPUT_NAMES") and not hasattr(capabilities, "OUTPUT_NAMES")
    for name in ("auto", "project", "business_report", "ab"):
        assert EngineSettings(output=name).output == name and TaskSettings(J2_OUTPUT=name).J2_OUTPUT == name
    for bad in ("Website", "", "a", "1abc", "has space", "x" * 42, "../etc"):
        with pytest.raises(ValueError):
            EngineSettings(output=bad)
        with pytest.raises(ValueError):
            TaskSettings(J2_OUTPUT=bad)
