"""The agent documents (agent_prd, agent_hld, agent_lld) and what the engine needs to chain them and to plan a folder build
without a web page's words.

1. The three templates are valid sources (the engine's own check).
2. A finished agent document gives the next one its numbered items (requirements, actions, must-never-do rules, steps,
   components), read from the document's own template: no type is named in the parser.
3. The next document's charter carries every earlier document's ids under "<type>_ids", so a chain-ids condition can tell
   that a requirement is missing from the components or from the tests.
4. A folder build's plan format asks for files, with the folder form's check types: no section id, class name, selector or
   date control. A page's format and a document's are what they were.
5. A folder builder's state has no page sections and no style guide.
"""
import itertools
import json
from pathlib import Path

import pytest

from test_engine_patches import fresh_j2

ENGINE_DIR = Path(__file__).resolve().parents[2] / "sutra_app" / "engine"
DOCS = ("agent_prd", "agent_hld", "agent_lld")
FT = "inbox_agent"

PRD = """# Agent PRD

## Goals

- **G1**: No urgent email waits more than 15 minutes unseen

## Requirements

1. **R1**: Reads only emails received since the last run (must). Accepted when a second run posts nothing. Checked by test_run. Serves G1.
2. **R2**: Posts one digest of at most 10 emails (must). Accepted when one Slack message exists. Checked by test_run. Serves G1.

## Actions and authority

| Id | Action | System | Access | Authority | Reversible | Serves |
|---|---|---|---|---|---|---|
| A1 | read new email | the mailbox | read | autonomous | yes | R1 |
| A2 | post the digest | Slack channel #inbox-digest | write | autonomous | yes | R2 |

## Must never do

- **N1**: Post to any channel other than #inbox-digest. Shown by: no Slack call names another channel.
"""

HLD = """# Agent HLD

## Steps

1. **S1** Fetch (code): read new mail. Implements R1.
2. **S2** Rank and post (model): score and post. Implements R2.

## Components

- **C1** Fetcher (tool): reads emails since the last run. Covers R1. In S1. Performs A1.
- **C2** Poster (tool): posts the digest to the channel. Covers R2. In S2. Performs A2.
"""


@pytest.fixture(scope="module")
def j2(tmp_path_factory):
    with fresh_j2(tmp_path_factory.mktemp("j2-agent-docs")) as mod:
        yield mod


@pytest.fixture(scope="module")
def j2ft(tmp_path_factory):
    """J2 with a folder type made in its own type store, as Adaptation makes one for an agent."""
    base = tmp_path_factory.mktemp("j2-agent-ft")
    with fresh_j2(base, J2_TYPES_DIR=base / "types") as mod:
        mod.j2_types.create(FT, "Inbox agent", None, form="agent")
        mod._data_type.cache_clear()
        yield mod


def ids(items):
    return [x["id"] for x in items]


# ---- 1. the templates
def test_the_three_agent_templates_are_valid_sources(j2):
    assert j2.j2_template_lib.generic_problems(list(DOCS)) == []


@pytest.mark.parametrize("name, sections", [("agent_prd", 16), ("agent_hld", 9), ("agent_lld", 7)])
def test_each_agent_type_loads_with_its_sections_files_and_conditions(j2, name, sections):
    out = j2.j2_types.load(name)
    assert len(out["sections"]) == sections and out["conditions"] == f"{name}.json"
    cond = json.loads((ENGINE_DIR / "conditions" / f"{name}.json").read_text(encoding="utf-8"))
    assert cond["output"] == name and all(c.get("check") and c.get("text") for c in cond["conditions"])
    for part in ("builder.md", "intake.md", "charter.txt", "atom_rules.md", "generic.json"):
        assert (ENGINE_DIR / "templates" / name / part).is_file(), part


def test_the_agent_documents_cite_each_other_and_never_a_website_document(j2):
    assert j2.j2_types.cites("agent_hld") == {"Steps": ("agent_prd", "requirements", "implements"),
                                              "Components": ("agent_prd", "requirements", "covers")}
    lld = j2.j2_types.cites("agent_lld")
    assert lld["Tests"] == ("agent_prd", "requirements", "covers") and lld["Tools"] == ("agent_hld", "components", "component")
    assert {d for name in DOCS for d, _, _ in j2.j2_types.cites(name).values()} <= {"agent_prd", "agent_hld"}


def test_the_planner_can_tell_the_website_documents_from_the_agent_ones_by_their_labels(j2):
    labels = {t["name"]: t["label"] for t in j2.j2_realization.type_list()}
    assert [labels[n] for n in ("prd", "hld", "lld")] == ["Website product requirements", "Website high-level design",
                                                          "Website low-level design"]
    assert [labels[n] for n in DOCS] == ["Agent product requirements", "Agent high-level design", "Agent low-level design"]


# ---- 2. what a finished agent document hands on
def test_an_agent_prd_hands_on_every_numbered_list_of_its_template(j2):
    ao = j2.doc_agent_output("agent_prd", PRD)
    assert ao["kind"] == "agent_prd"
    assert (ids(ao["requirements"]), ids(ao["actions"]), ids(ao["never"]), ids(ao["goals"])) == (
        ["R1", "R2"], ["A1", "A2"], ["N1"], ["G1"])
    assert ao["requirements"][0]["text"].startswith("Reads only emails received since the last run")
    assert ao["actions"][1]["text"].startswith("post the digest | Slack channel #inbox-digest | write")
    assert ao["failures"] == [] and ao["cases"] == []      # sections the document leaves empty


def test_an_agent_hld_hands_on_its_steps_and_components(j2):
    ao = j2.doc_agent_output("agent_hld", HLD)
    assert (ao["kind"], ids(ao["steps"]), ids(ao["components"])) == ("agent_hld", ["S1", "S2"], ["C1", "C2"])


def test_an_id_inside_a_sentence_is_not_an_item(j2):
    text = PRD.replace("Serves G1.\n2. **R2**", "Serves G1. See R7 too.\n2. **R2**")
    assert ids(j2.doc_agent_output("agent_prd", text)["requirements"]) == ["R1", "R2"]


def test_the_website_documents_and_a_document_without_numbered_items_are_read_as_before(j2):
    assert j2.doc_agent_output("prd", "## Requirements\n\n1. **R1**: Shows the menu (must).\n") == {
        "kind": "prd", "requirements": [{"id": "R1", "text": "Shows the menu (must)."}]}
    assert j2.doc_agent_output("hld", "## Components\n\n- **C1** Menu: shows the menu. Covers R1.\n")["kind"] == "hld"
    assert j2.doc_agent_output("lld", "")["kind"] == "lld"
    assert not j2.j2_types.id_prefixes("business_report") and j2.doc_agent_output("business_report", "## Summary\n\nx\n")["kind"] == "lld"


# ---- 3. the chain
def test_the_next_charter_carries_every_earlier_documents_ids(j2):
    chain = {"agent_prd": j2.doc_agent_output("agent_prd", PRD)}
    goal = j2.stage_goal("agent_hld", {"product_name": "Inbox digest"}, chain)
    assert goal["chain"]["agent_prd_ids"] == ["R1", "R2"] and goal["chain"]["prd_ids"] == []
    assert any("names every requirement (R1, R2) it covers" in item for item in goal["done_when"])
    chain["agent_hld"] = j2.doc_agent_output("agent_hld", HLD)
    goal = j2.stage_goal("agent_lld", {"product_name": "Inbox digest"}, chain)
    assert goal["chain"]["agent_hld_ids"] == ["C1", "C2"] and goal["chain"]["agent_prd_ids"] == ["R1", "R2"]


def cond_of(name, cid):
    data = json.loads((ENGINE_DIR / "conditions" / f"{name}.json").read_text(encoding="utf-8"))
    return next(c for c in data["conditions"] if c["id"] == cid)


def test_a_requirement_no_component_covers_fails_the_agent_hld(j2):
    goal = {"chain": {"agent_prd_ids": ["R1", "R2"]}}
    cond = cond_of("agent_hld", "AH5")
    assert j2.condition_met(cond, HLD, goal, "", ())[0] is True
    met, why = j2.condition_met(cond, HLD.replace(" Covers R2.", ""), goal, "", ())
    assert met is False and "R2" in why


def test_a_requirement_no_test_proves_fails_the_agent_lld(j2):
    goal = {"chain": {"agent_prd_ids": ["R1", "R2"]}}
    lld = "## Tests\n\n- **X1** (run): with a fake mailbox, expects one message. Covers R1.\n"
    met, why = j2.condition_met(cond_of("agent_lld", "AL4"), lld, goal, "", ())
    assert met is False and "R2" in why
    assert j2.condition_met(cond_of("agent_lld", "AL4"), lld.replace("Covers R1.", "Covers R1, R2."), goal, "", ())[0] is True


# ---- 4. a folder build's plan format
PAGE_WORDS = ("section id", "class name", "site section", "selector", "date_control", "a new section", "element-count",
              "grep-count", "section/element")


@pytest.fixture
def run_of(tmp_path):
    counter = itertools.count(1)

    def make(mod, output):
        run = mod.J2Run(run_dir=tmp_path / "runs" / f"j2-20261126-1900{next(counter):02d}-a9e1")
        run._apply_output(output)
        return run
    return make


def test_the_page_format_still_holds_the_words_the_folder_format_replaces(j2):
    """The folder format is the page format with these exact words replaced: if J2 rewords one, this fails first."""
    for words in ("whose site section this one rewrites; null adds a new section)", "naming every section id and class name it creates)",
                  '"date_control": str|null (when it covers a done-when item whose rule depends on a date and its output is a page',
                  ' (section/element only, default 1)', ', "steps": [str] (behavior only)', '"R-6"'):
        assert words in j2.J2Run.WF_FMT, words


def test_a_folder_builds_plan_format_asks_for_files_and_nothing_of_a_page(j2ft, run_of):
    run = run_of(j2ft, FT)
    assert run.folder and not run.doc
    for fmt in (run.WF_FMT, run.GRANT_FMT):
        assert not [w for w in PAGE_WORDS if w in fmt], fmt
        assert "naming every file it writes, each a path inside the folder" in fmt
        assert "whose files this one rewrites; null adds new files" in fmt
        assert '"date_case": str|null (when it covers a done-when item whose rule depends on a date: the test case' in fmt
        assert all(f'"{t}"' in fmt for t in ("file-exists", "test-passed", "inside-folder", "facts-present"))
        assert '"A-1"' in fmt and '"R-6"' not in fmt


def test_a_pages_format_and_a_documents_are_what_they_were(j2, run_of):
    page = run_of(j2, "website")
    assert page.WF_FMT == j2.J2Run.WF_FMT and page.GRANT_FMT == j2.J2Run.GRANT_FMT
    doc = run_of(j2, "prd")
    assert '"sections": [str] (the section(s) it writes' in doc.WF_FMT and "naming every section id and class name it creates" in doc.WF_FMT


# ---- 5. a folder builder's state
def test_a_folder_builders_state_has_no_page_sections_and_no_style_guide(j2ft, j2, run_of):
    state = json.loads(run_of(j2ft, FT).builder_state("W-1 Builder"))
    assert "site_sections" not in state and "style_guide" not in state and "charter" in state and "requester_brief" in state
    page = json.loads(run_of(j2, "website").builder_state("W-1 Builder"))
    assert "site_sections" in page and "style_guide" in page and "charter" in page


# ---- 6. a folder built after the documents: its charter is what the documents say
LLD = """# Agent LLD

## Tools

- **T1** `slack_post_digest` (on C2, write): posts the digest. Returns the message id. On error: an error text.

## Limits

- At most 3 steps
- At most 60 s per unit
- At a limit: stop and post nothing

## File structure

- `run.py`: the entry point. States N1.
- `inbox_agent/pulse/digest.py`: builds the digest.
- `./tests/run_all.py`: runs every test. Runs the tests: yes.
- `tests/test_digest.py`: the digest cases.
- `../outside.py`: never listed.

## Tests

- **X1** (run): with a fake mailbox, expects one message. Covers R1, R2.
"""


def test_the_files_a_document_lists_are_read_from_its_own_template(j2):
    files = j2.doc_files("agent_lld", LLD)
    assert [f["path"] for f in files] == ["run.py", "inbox_agent/pulse/digest.py", "./tests/run_all.py", "tests/test_digest.py",
                                          "../outside.py"]
    assert [f["path"] for f in files if f["test"]] == ["./tests/run_all.py"]
    assert j2.doc_files("agent_prd", PRD) == [] and j2.doc_files("agent_hld", HLD) == []


def staged(mod, run, texts):
    """`run` as it stands when the documents in `texts` are finished and the folder stage begins."""
    import os
    os.makedirs(run.dir, exist_ok=True)
    run.docs, run.chain = {}, {}
    for kind, text in texts.items():
        with open(os.path.join(run.dir, f"{kind}.md"), "w", encoding="utf-8") as f:
            f.write(text)
        run.docs[kind] = {"file": f"{kind}.md"}
        run.chain[kind] = mod.doc_agent_output(kind, text)
    run.stage_archive = [{"goal": {"product_name": "Inbox digest", "users": "the founder"}}]
    return run


def test_a_folder_after_the_documents_gets_its_files_test_and_rules_from_them(j2ft, run_of):
    run = staged(j2ft, run_of(j2ft, FT), {"agent_prd": PRD, "agent_hld": HLD, "agent_lld": LLD})
    goal = run._folder_stage_goal(FT)
    # the folder's own name in front of a path is dropped, "./" too; a path that leaves the folder is never listed
    assert goal["files"] == ["run.py", "pulse/digest.py", "tests/run_all.py", "tests/test_digest.py"]
    assert goal["test"] == "tests/run_all.py"
    assert goal["never_do"] == ["Post to any channel other than #inbox-digest"]
    assert [x.split(":")[0] for x in goal["may_touch"]] == ["A1", "A2"] and "Slack channel #inbox-digest" in goal["may_touch"][1]
    assert goal["done_when"] == [f"{p} is in the folder" for p in goal["files"]] + ["The test tests/run_all.py passes when code runs it"]
    assert goal["item_checks"]["run.py is in the folder"] == {"type": "file-exists", "target": "run.py", "expect": True}
    assert goal["item_checks"][goal["done_when"][-1]] == {"type": "test-passed", "target": "tests/run_all.py", "expect": True}
    assert set(goal["item_checks"]) == set(goal["done_when"]) and len(goal["core"]) == len(goal["done_when"])
    assert "At most 3 steps" in goal["design"]["Limits"] and "Tools" not in goal["design"]      # what the chain does not hand on
    assert goal["chain"]["agent_prd_ids"] == ["R1", "R2"] and goal["statement"].startswith("Inbox agent for Inbox digest, built from")
    assert "PULSE" not in goal["statement"] and goal["product_name"] == "Inbox digest"


def test_the_folder_conditions_can_be_met_from_that_charter(j2ft, run_of):
    """The two gates that read the charter (the files, the test) have something to read."""
    run = staged(j2ft, run_of(j2ft, FT), {"agent_prd": PRD, "agent_lld": LLD})
    goal = run._folder_stage_goal(FT)
    assert j2ft.charter_list(goal, "files") == goal["files"] and j2ft.charter_list(goal, "test") == ["tests/run_all.py"]
    assert j2ft.charter_list(goal, "never_do") == goal["never_do"]


def test_without_a_marked_file_the_first_test_file_runs_the_tests_and_without_any_there_is_no_charter(j2ft, run_of):
    run = staged(j2ft, run_of(j2ft, FT), {"agent_lld": LLD.replace(" Runs the tests: yes.", "")})
    assert run._folder_stage_goal(FT)["test"] == "tests/test_digest.py"
    none = LLD.replace(" Runs the tests: yes.", "").replace("`tests/test_digest.py`", "`cases/digest.py`").replace(
        "`./tests/run_all.py`", "`cases/all.py`")
    assert staged(j2ft, run_of(j2ft, FT), {"agent_lld": none})._folder_stage_goal(FT) is None
    assert staged(j2ft, run_of(j2ft, FT), {"agent_prd": PRD})._folder_stage_goal(FT) is None      # no document lists files


def test_a_folders_plan_rules_say_how_a_path_is_written(j2ft, j2, run_of):
    rules = run_of(j2ft, FT).ATOM_RULES
    assert f'never "{FT}/run.py"' in rules and "PATHS:" in rules
    assert "PATHS:" not in run_of(j2, "website").ATOM_RULES and "PATHS:" not in run_of(j2, "prd").ATOM_RULES
