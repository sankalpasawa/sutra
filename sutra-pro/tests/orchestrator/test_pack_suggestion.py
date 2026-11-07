"""Suggesting a practice pick when a team is added (GAP2 rules-notes): the old Adaptation floor "proposes templates from its use case", in code.

The turn runner runs for real over the scripted connector and the fake launcher (test_turn_runner's `RunnerEnv`). The card is a code-written template
question with Yes and No; Yes puts the pick on the team, No is remembered, and nothing changes without the click."""
import pytest
from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
from orchestrator.test_turn_runner import renv  # noqa: F401  (renv is a fixture)

from sutra_app.library.practice import load_packs
from sutra_app.orchestrator.agent import planner
from sutra_app.orchestrator.agent.suggest import card_for, pack_ref, parse_ref, suggest_pack
from sutra_app.orchestrator.errors import AlreadyDecided
from sutra_app.orchestrator.models import ChatChoice
from sutra_app.orchestrator.standing_rules import StandingRules

PACKS = load_packs()
MONEY = "money-movement"


def add_team(renv, name="Servicing", purpose="Handles payments, refunds and EMI collections", dept="servicing"):
    renv.connector.push(decide(change="add", reuse=()), change_reply(add_dept("$t", name, purpose)), assignments(draft("a1", dept)))
    return renv.say(f"Set up {name} for me")


def spy(renv):
    """Keep the `_Applied` of each add the runner hands to the suggestion, so a test can offer the same one again."""
    seen = []
    original = renv.runner._suggest_packs
    renv.runner._suggest_packs = lambda applied: (seen.append(applied), original(applied))[1]
    return seen


def card_id(renv):
    return next(m.id for m in renv.messages() if m.kind == "card" and m.card.type == "choice")


# ---- the matching ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,purpose,expected", [
    ("Servicing", "Handles payments, refunds and EMI collections", MONEY),
    ("Billing", "Sends invoices and tracks payments", MONEY),
    ("Product", "Builds and ships the app to users", "product-build"),
    ("Launch", "Plans each release and ships new features", "product-build"),
    ("Web", "Websites, landing pages and menus", None),
    ("Cafe Site", "Menu pages and opening hours", None),
    ("Billing", "Sends reminders", None),                       # one shared word is never enough
    ("Payments", "Refunds, ships to users", None),               # two packs fit equally (two words each): a tie suggests nothing
    ("Payments app", "Ships payments to users", "product-build"),                    # the better fit wins when one is clearly ahead
    ("", "", None),
])
def test_a_team_is_matched_by_its_name_and_purpose_words_and_conservatively(name, purpose, expected):
    found = suggest_pack(name, purpose, PACKS)
    assert (found.id if found else None) == expected


def test_the_card_is_a_template_question_and_its_ref_round_trips():
    card = card_for("Servicing", PACKS[0])
    assert card == {"type": "choice", "question": "The Servicing team looks like it moves or posts money. Run it with the Money movement practice?",
                    "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]}
    assert planner.matches_template(card["question"]) and planner.matches_template(planner.line("pack_yes", name="A", pack="B"))
    assert planner.matches_template(planner.line("pack_no", name="A"))
    assert parse_ref(pack_ref("servicing", MONEY)) == ("servicing", MONEY)
    for bad in ("req:5:choice", "pack:Servicing:x", "pack:servicing:", "", None):
        assert parse_ref(bad) is None


# ---- through the org chat --------------------------------------------------------------------------------------------------------------

def test_a_payments_team_gets_the_card_after_the_add_and_a_website_team_gets_none(renv):
    add_team(renv)
    assert renv.sutra()[-4:] == [("text", "I set up a Servicing team and gave it your request."), ("card", "chart_change"), ("card", "task"), ("card", "choice")]
    card = renv.cards("choice")[-1]
    assert card.question == "The Servicing team looks like it moves or posts money. Run it with the Money movement practice?"
    assert [o.id for o in card.options] == ["yes", "no"]
    assert renv.one("SELECT src_ref FROM chat_messages WHERE id = ?", card_id(renv)) == "pack:servicing:money-movement"
    assert StandingRules(renv.db).get("servicing").pack is None                              # nothing changes without the click
    before = len(renv.cards("choice"))
    add_team(renv, "Cafe Site", "Menu pages and opening hours", "cafe-site")
    assert len(renv.cards("choice")) == before                                               # a website team: no card


def test_the_org_chat_still_holds_only_template_sentences(renv):
    add_team(renv)
    renv.say("Yes", choice=ChatChoice(message_id=card_id(renv), option="yes"))
    spoken = [m.card.question if m.kind == "card" else m.text for m in renv.messages() if m.who == "sutra" and (m.kind != "card" or m.card.type == "choice")]
    assert len(spoken) == 4                                                                   # greeting, the add line, the question, the answer
    assert all(planner.matches_template(text) for text in spoken), spoken


def test_yes_puts_the_pick_on_the_team_and_the_next_run_carries_it(renv):
    add_team(renv)
    renv.say("Yes", choice=ChatChoice(message_id=card_id(renv), option="yes"))
    assert renv.sutra()[-1] == ("text", "The Servicing team now runs the Money movement practice.")
    state = StandingRules(renv.db).get("servicing")
    assert state.pack.id == MONEY and state.declined == []
    assert [(m.who, m.text) for m in renv.messages() if m.role == "user"][-1] == ("user", "Yes")
    first = renv.one("SELECT id FROM tasks WHERE dept_id = 'servicing' ORDER BY created_at LIMIT 1")
    renv.projector.mark_ended(first, "done", "ok")                                            # one live task per team: the first one ends
    follow = renv.new("servicing", "Pay the supplier run")
    renv.run(renv.service.start_ready())
    spec = (renv.run_dir(follow.id) / "task.json").read_text()
    assert "Practice \\\"Money movement\\\"" in spec and "Standing rules from the owner" in spec


def test_no_leaves_the_team_on_the_defaults_and_it_is_not_asked_again(renv):
    seen = spy(renv)
    add_team(renv)
    renv.say("No", choice=ChatChoice(message_id=card_id(renv), option="No"))
    assert renv.sutra()[-1] == ("text", "Okay, the Servicing team stays on the defaults.")
    state = StandingRules(renv.db).get("servicing")
    assert state.pack is None and state.declined == [MONEY]
    cards = len(renv.cards("choice"))
    renv.runner._suggest_packs(seen[0])                                                       # the same add again: the earlier no is respected
    assert len(renv.cards("choice")) == cards
    assert not renv.sql("SELECT 1 FROM tasks WHERE dept_id = 'servicing' AND framing LIKE '%Standing rules%'").fetchall()


def test_a_team_that_already_wears_a_pick_is_not_asked(renv):
    seen = spy(renv)
    add_team(renv)
    StandingRules(renv.db).accept("servicing", MONEY)
    cards = len(renv.cards("choice"))
    renv.runner._suggest_packs(seen[0])
    assert len(renv.cards("choice")) == cards


def test_a_card_answered_once_cannot_be_answered_again(renv):
    add_team(renv)
    cid = card_id(renv)
    renv.say("Yes", choice=ChatChoice(message_id=cid, option="yes"))
    with pytest.raises(AlreadyDecided):
        renv.say("No", choice=ChatChoice(message_id=cid, option="no"))
    assert StandingRules(renv.db).get("servicing").pack.id == MONEY


def test_a_button_that_is_not_on_the_card_is_refused(renv):
    add_team(renv)
    with pytest.raises(Exception) as caught:
        renv.say("Maybe", choice=ChatChoice(message_id=card_id(renv), option="maybe"))
    assert getattr(caught.value, "code", "") == "validation"


def test_a_failed_suggestion_never_fails_the_turn(renv, monkeypatch):
    monkeypatch.setattr("sutra_app.orchestrator.agent.runner.load_packs", lambda: (_ for _ in ()).throw(RuntimeError("broken file")))
    accepted = add_team(renv)
    assert renv.user_state(accepted.message_id) == "ok" and renv.sutra()[-1] == ("card", "task")
