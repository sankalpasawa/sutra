"""The practice packs and the text a team reads (GAP2 rules-notes): the old function templates' use-case floors as starter picks.

The law of the old `test_function_templates.py` is re-expressed for Pro's words: a pack only ADDS to a team's defaults and never drops or loosens
(`test_narrowing_only`), its lines use none of the words the screen does not say (`test_screen_words`), a check is never a score, and Priority never
orders the queue. `compose_*` is the text the engine host posts as "Context from the team lead"."""
import pytest
from pydantic import ValidationError

from sutra_app.library import practice
from sutra_app.library.practice import (
    BLOCK_CHARS, BLOCK_HEADING, MAX_PACK_LINES, PackLine, PracticePack, RuleLine, block_of, clean_text, compose_block, compose_framing,
    law_problems, load_packs, normalise, pack_by_id, rank, rule_faults,
)
from sutra_app.library.types import FUNCTIONS


def pack(lines, pack_id="test-pack"):
    return PracticePack(id=pack_id, name="Test", use_case="A test pick.", fits="does a test", keywords=["alpha", "beta", "gamma"], lines=lines)


def line(function="audit", tag="always", text="Checks every claim against its source."):
    return PackLine(function=function, tag=tag, text=text)


# ---- the shipped packs ---------------------------------------------------------------------------------------------------------

def test_the_two_starter_packs_are_shipped_and_keep_the_law():
    packs = load_packs()
    assert [p.id for p in packs] == ["money-movement", "product-build"]
    assert law_problems(packs) == []
    assert pack_by_id("money-movement").name == "Money movement" and pack_by_id("nope") is None and pack_by_id(None) is None


def test_every_pack_adds_something_for_each_of_the_five_functions_and_within_the_cap():
    for found in load_packs():
        for fn in FUNCTIONS:
            mine = [l for l in found.lines if l.function == fn]
            assert 1 <= len(mine) <= MAX_PACK_LINES, (found.id, fn)
        assert all(len(l.text) <= 300 for l in found.lines)


def test_the_old_use_case_floor_lines_are_carried_in_pros_words():
    text = " ".join(l.text for l in pack_by_id("money-movement").lines)
    assert "payment above the owner's line is put to the owner and never done on its own" in text
    assert "names its source record" in text and "one makes, another checks" in text
    ship = " ".join(l.text for l in pack_by_id("product-build").lines)
    assert "promise to a user outside the team" in ship and "judged against the done line" in ship


def test_a_pack_line_is_never_looser_than_ask_so_the_defaults_stay_whole():
    """The tag set has no `go`: a pack cannot permit what a default forbids. Every line asks, requires or forbids."""
    assert {l.tag for p in load_packs() for l in p.lines} <= {"always", "ask", "never"}
    with pytest.raises(ValidationError):
        PackLine(function="audit", tag="go", text="Anything goes.")
    with pytest.raises(ValidationError):
        PackLine(function="finance", tag="always", text="Not one of the five.")


# ---- the law, one breach at a time -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,fragment", [
    ("Refuse a payment above the line.", "word the screen does not say"),
    ("The charter holds the rule.", "word the screen does not say"),
    ("The Root team signs it.", "word the screen does not say"),
    ("The engine records it.", "word the screen does not say"),
    ("Rule D12 applies here.", "founder-only id"),
    ("Skips the check when it is late.", "loosens"),
    ("Pays without asking the owner.", "loosens"),
    ("Waives the approval for small amounts.", "loosens"),
    ("Gives every check a score out of ten.", "treats a check as a score"),
])
def test_a_line_that_breaks_the_law_is_named(text, fragment):
    problems = law_problems([pack([line(text=text)])])
    assert len(problems) == 1 and fragment in problems[0], problems


def test_a_check_may_say_it_is_never_a_score():
    assert law_problems([pack([line(text="A check is never a score; it has a verdict and its evidence.")])]) == []


def test_priority_never_orders_the_queue():
    problems = law_problems([pack([line("priority", text="Puts the urgent task first in the order of work.")])])
    assert len(problems) == 1 and "Coordination" in problems[0]
    assert law_problems([pack([line("coordination", text="Puts the urgent task first in the order of work.")])]) == []


def test_a_pack_that_repeats_a_line_or_runs_past_the_cap_is_named():
    again = pack([line(text="Checks every claim."), line(text="checks every  claim")])
    assert any("says one line twice" in p for p in law_problems([again]))
    many = pack([line(text=f"Checks claim number {n} against its source.") for n in range(MAX_PACK_LINES + 1)])
    assert any(f"at most {MAX_PACK_LINES}" in p for p in law_problems([many]))
    assert any("used twice" in p for p in law_problems([pack([line()]), pack([line(text="Another line entirely.")])]))
    assert any("two functions say one line" in p for p in law_problems([pack([line("audit"), line("identity")])]))


# ---- comparing lines (the old tighten.py) ----------------------------------------------------------------------------------------

def test_lines_are_compared_as_normalised_text():
    assert normalise("Never publish prices.") == normalise("publish  PRICES") == "publish prices"
    assert normalise("Don’t email clients") == "email clients"
    assert clean_text("a\n\n b\t\x00 c ") == "a b c"


def test_ranks_and_the_rule_that_says_the_same_line_more_loosely():
    assert (rank("ask", "x"), rank("never", "x"), rank("always", "Never do x"), rank("always", "Do x")) == (1, 2, 2, None)
    inherited = [("never", "Never publish prices.")]
    assert len(rule_faults(inherited, "ask", "publish prices")) == 1                 # asks first: looser than never
    assert "A rule cannot say it more loosely" in rule_faults(inherited, "ask", "publish prices")[0]
    assert rule_faults(inherited, "never", "Publish prices") == []                    # as strict
    assert rule_faults(inherited, "always", "Never publish prices") == []             # a prohibition is as strict
    assert rule_faults(inherited, "ask", "something else entirely") == []             # another line: not compared
    assert rule_faults([("always", "Check the totals")], "ask", "Check the totals") == []     # a positive requirement has no rank


# ---- the text a team reads -------------------------------------------------------------------------------------------------------

def test_nothing_to_say_is_no_text_at_all():
    assert compose_block([], None) == ""
    assert compose_framing([], None, "The owner wants it Friday.", 20_000) == "The owner wants it Friday."
    assert compose_framing([], None, "", 20_000) == ""


def test_the_owners_rules_come_grouped_in_front_then_the_pick_per_function():
    rules = [RuleLine(tag="never", text="Never email a client without asking."), RuleLine(tag="always", text="Use plain words."),
             RuleLine(tag="ask", text="Ask before a purchase.")]
    block = compose_block(rules, pack_by_id("money-movement"))
    lines = block.split("\n")
    assert lines[0].startswith(BLOCK_HEADING) and lines[1:4] == [
        "- Always: Use plain words.", "- Ask the owner first: Ask before a purchase.", "- Never: Never email a client without asking."]
    assert lines[4] == "Practice \"Money movement\" (added to the defaults, never loosening them):"
    functions = [l.split(",")[0].removeprefix("- ").lower() for l in lines[5:]]
    assert functions == sorted(functions, key=FUNCTIONS.index)
    assert "- Identity, ask the owner first: A payment above the owner's line" in block


def test_a_pick_alone_and_rules_alone_both_read_well():
    assert compose_block([], pack_by_id("product-build")).startswith(BLOCK_HEADING) and "Practice \"Product build\"" in compose_block([], pack_by_id("product-build"))
    only = compose_block([RuleLine(tag="always", text="Be brief.")], None)
    assert only.count("\n") == 1 and "Practice" not in only


def test_the_block_is_in_front_of_the_brief_and_found_again():
    rules = [RuleLine(tag="never", text="Never share prices.")]
    framing = compose_framing(rules, None, "Build the cafe page.", 20_000)
    assert framing.startswith(BLOCK_HEADING) and framing.endswith("\n\nBuild the cafe page.")
    assert block_of(framing) == compose_block(rules, None)
    assert block_of("Build the cafe page.") == "" and block_of("") == ""


def test_the_block_never_runs_past_its_cap_and_keeps_the_owners_rules_whole(monkeypatch):
    rules = [RuleLine(tag="always", text=("rule %02d " % n) + "x" * 292) for n in range(20)]            # twenty lines of the full 300 characters
    assert all(len(r.text) == 300 for r in rules)
    assert len(compose_block(rules, pack_by_id("money-movement"))) <= BLOCK_CHARS                       # the largest honest block fits as it is
    monkeypatch.setattr(practice, "BLOCK_CHARS", 7000)                                                   # a tighter cap shows what is cut
    block = compose_block(rules, pack_by_id("money-movement"))
    assert len(block) <= 7000
    assert all(f"- Always: rule {n:02d} " in block for n in range(20))                    # the owner's lines are never the part cut
    assert block.endswith("(more lines were left out)")                                    # the pick's tail was


def test_a_long_brief_is_squeezed_in_the_middle_never_the_block_and_never_its_two_ends():
    rules = [RuleLine(tag="never", text="Never share prices.")]
    brief = "START " + "m" * 30_000 + " This is attempt 2 of this request."
    framing = compose_framing(rules, None, brief, 20_000)
    assert len(framing) <= 20_000 and framing.startswith(BLOCK_HEADING)
    assert "START " in framing and framing.endswith("This is attempt 2 of this request.") and " [...] " in framing
    assert compose_framing(rules, None, "", 100).startswith(BLOCK_HEADING) and len(compose_framing(rules, None, "", 100)) <= 100


def test_the_module_imports_nothing_from_the_rest_of_the_app():
    source = open(practice.__file__, encoding="utf-8").read()
    assert "sutra_app.orchestrator" not in source and "sutra_app.connectors" not in source and "sutra_app.engine" not in source
