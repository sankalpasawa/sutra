"""The engine chooses the output itself (work package WP4, engine design 2.4, D129): a pure rule table in `capabilities/select.py`, decided
once by the host before J2 starts. No model call, so the table is tested as a table of briefs."""
import pytest

from sutra_app.engine import capabilities
from sutra_app.engine.capabilities.select import RULES, STRONG_PROJECT_WORDS, chat_line, choose_output

# (brief, a working folder is set, the output of the run this continues, the owner's choice) -> (output, rule)
TABLE = [
    # the owner's own sentences
    ("check the details of the app and update the J2 prototype in the repo", True, None, "auto", "project", "project"),
    ("check the details of the app and update the J2 prototype in the repo", False, None, "auto", "project", "project"),
    ("check the details of the app and update the J2 prototype", True, None, "auto", "project", "folder"),
    ("build a florist site", False, None, "auto", "website", "deliver"),
    ("build a florist site", True, None, "auto", "website", "deliver"),
    ("update the PRD in the repo", True, None, "auto", "project", "project"),
    ("update the PRD in the repo", False, None, "auto", "project", "project"),
    # named documents with no folder: as before (J2's own detect_documents plans them)
    ("Write a PRD for QuickQueue, a mobile app for clinics", False, None, "auto", "website", "deliver"),
    ("draft the HLD and the LLD for a bakery site", False, None, "auto", "website", "deliver"),
    ("Create design docs for a yoga studio website", False, None, "auto", "website", "deliver"),
    # the start page's own examples are websites, with or without a folder
    ("A website for my cafe", False, None, "auto", "website", "deliver"),
    ("A website for Petal & Stem, a florist in Jaipur: bouquets, same-day delivery", True, None, "auto", "website", "deliver"),
    # nothing about a project and no folder: today's behaviour
    ("a cafe called Brew Lab with a menu and opening hours", False, None, "auto", "website", "default"),
    ("hello", False, None, "auto", "website", "default"),
    ("", False, None, "auto", "website", "default"),
    # a folder is set and the request is not a make-a-thing request
    ("look at the app and tell me what is missing", True, None, "auto", "project", "folder"),
    ("update the J2 prototype", True, None, "auto", "project", "folder"),
    # strong project words, each on its own
    ("fix the bug in checkout", False, None, "auto", "project", "weak"),
    ("refactor the login module", False, None, "auto", "project", "project"),
    ("what changed in the last commit?", False, None, "auto", "project", "project"),
    ("open a pull request for the rename", False, None, "auto", "project", "project"),
    ("create a new branch for the redesign", False, None, "auto", "project", "project"),
    ("read CLAUDE.md and follow it", False, None, "auto", "project", "project"),
    ("summarise the codebase", False, None, "auto", "project", "project"),
    ("list the files in the folder", False, None, "auto", "project", "project"),
    ("check the app's code for TODOs", False, None, "auto", "project", "project"),
    ("update the Source of truth", False, None, "auto", "project", "weak"),
    ("GIT status please", False, None, "auto", "project", "project"),
    # a follow-up keeps its output, even when its words are about a bug
    ("make the header blue", False, "website", "auto", "website", "followup"),
    ("fix the bug in the contact form", True, "website", "auto", "website", "followup"),      # a weak word does not leave a website follow-up
    ("update the J2 prototype in the repo", True, "website", "auto", "project", "project"),   # a repository word does: a team whose first run was a site intake
    ("look at the folder and the git log", False, "website", "auto", "project", "project"),
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
def test_every_strong_word_of_the_design_picks_project_work(word):
    assert choose_output(f"please look at the {word} now", False).output == "project"


@pytest.mark.parametrize("brief", ["a debugging guide for the bakery", "the budget for the florist", "digital marketing for a gym",
                                   "a legit coffee shop", "an aggregate of orders", "the resourceful florist"])
def test_a_word_that_only_contains_a_strong_word_does_not_count(brief):
    assert choose_output(brief, False).rule not in ("project",), brief


def test_the_reason_says_what_the_owner_asked_about():
    assert choose_output("update the repo", False).reason == "you asked about a repository"
    assert choose_output("fix the bug", False).reason == "you asked about a bug"
    assert "working folder" in choose_output("look around", True).reason


def test_the_table_is_pure_and_the_same_every_time():
    args = ("check the details of the app and update the J2 prototype in the repo", True, None, "auto")
    assert choose_output(*args) == choose_output(*args)


def test_a_missing_brief_and_missing_seed_are_not_errors():
    assert choose_output(None, False).output == "website"          # type: ignore[arg-type]
    assert choose_output("x", False, "").rule == "default"


def test_the_words_are_data_and_each_has_a_reason_for_the_owner():
    assert all(pattern and why for pattern, why in STRONG_PROJECT_WORDS)


# ---- the chat line: only for project work ------------------------------------------------------------------------------
def test_a_website_selection_posts_nothing_so_existing_runs_keep_their_events():
    for brief in ("build a florist site", "hello", "A website for my cafe"):
        assert chat_line(choose_output(brief, False), False) is None


def test_a_project_selection_says_so_in_one_line_with_the_reason_and_the_way_out():
    line = chat_line(choose_output("update the PRD in the repo", True), True)
    assert line == ("Working on this as project work in your folder (you asked about a repository; choose another kind of result in the "
                    "start page if that is wrong).")


def test_project_work_with_no_folder_says_where_to_choose_one():
    line = chat_line(choose_output("update the PRD in the repo", False), False)
    assert "no working folder is set" in line and "Working folder" in line


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
    assert (got.output, got.rule) == ("project", "project")
    assert capabilities.select_output("build a florist site", ctx()).output == "website"


def test_the_registry_reads_the_owners_choice_from_the_settings_it_is_given():
    assert capabilities.select_output("update the PRD in the repo", ctx(output="prd")).output == "prd"


def test_with_no_capability_voting_the_website_is_the_answer():
    assert capabilities.select_output("x", ctx(), capabilities=[]).output == "website"


def test_the_output_names_are_one_list_the_settings_and_the_tasks_share():
    from sutra_app.engine.spec import OUTPUT_NAMES, EngineSettings
    from sutra_app.orchestrator.models import TaskSettings
    assert capabilities.OUTPUT_NAMES == OUTPUT_NAMES == ("auto", "website", "prd", "hld", "lld", "project")
    for name in OUTPUT_NAMES:
        assert EngineSettings(output=name).output == name and TaskSettings(J2_OUTPUT=name).J2_OUTPUT == name
    for bad in ("pdf", "Website", ""):
        with pytest.raises(ValueError):
            EngineSettings(output=bad)
        with pytest.raises(ValueError):
            TaskSettings(J2_OUTPUT=bad)
