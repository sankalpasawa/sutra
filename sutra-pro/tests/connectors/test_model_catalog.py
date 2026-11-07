"""The model catalog of the chat pill (gap package welcome-settings, item 4; ports the old app's test_model_catalog.py)."""
from __future__ import annotations

import pytest

from sutra_app.connectors import model_catalog
from sutra_app.connectors.base import EFFORTS
from sutra_app.connectors.budget import WINDOWS, window_for
from sutra_app.connectors.errors import ConnectorError
from sutra_app.connectors.model_catalog import ModelOption, claude_options, efforts_of, names_of, options_for

# What `printf '' | claude --model <id> -p --output-format text` accepted on Claude Code 2.1.308 (the tested version): the run dies on the missing
# prompt AFTER the model name was resolved, so no model turn is spent. A control id, `totally-bogus-model`, was refused ("doesn't recognize the
# model"). This list is the record: an id is added to the catalog only together with a new probe and a new line here.
VERIFIED_2_1_308 = frozenset({"best", "opus", "sonnet", "haiku", "fable", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
                              "claude-sonnet-4-6", "opus[1m]", "sonnet[1m]"})


def test_every_offered_claude_id_was_probed_on_the_tested_cli():
    offered = {o.slug for o in claude_options()}
    assert offered <= VERIFIED_2_1_308 and offered == VERIFIED_2_1_308
    assert model_catalog.PROBED_ON == "2.1.308"
    assert "totally-bogus-model" not in offered


def test_the_main_rows_come_first_with_a_note_each_and_the_rest_are_more_models():
    options = claude_options()
    assert [o.slug for o in options[:4]] == ["best", "opus", "sonnet", "haiku"] and {o.group for o in options[:4]} == {"main"}
    assert all(o.group == "more" for o in options[4:]) and len(options) == 11
    assert all(o.note and o.label for o in options)
    by = {o.slug: o for o in options}
    assert by["opus"].note == "most capable, slowest, highest cost" and by["haiku"].note.startswith("fastest and cheapest")
    assert by["opus[1m]"].group == "more" and by["claude-opus-4-8"].note == "pinned snapshot"


def test_every_offered_claude_model_has_a_context_window_that_the_budget_knows():
    for o in claude_options():
        assert o.context_window == WINDOWS["claude"][o.slug] > 0
        assert window_for("claude", o.slug)["source"] == "known"


def test_every_claude_model_takes_the_clis_five_efforts():
    assert all(o.efforts == list(EFFORTS) for o in claude_options())
    assert efforts_of(claude_options(), "haiku") == ["low", "medium", "high", "xhigh", "max"]


def test_efforts_follow_the_model_and_an_unknown_model_or_an_empty_list_is_not_narrowed():
    options = [ModelOption(slug="gpt-a", label="A", efforts=["low", "high"]), ModelOption(slug="gpt-b", label="B", efforts=[])]
    assert efforts_of(options, "gpt-a") == ["low", "high"]
    assert efforts_of(options, "gpt-b") == list(EFFORTS) and efforts_of(options, "nope") == list(EFFORTS) and efforts_of(options, None) == list(EFFORTS)


def test_a_model_option_is_closed():
    with pytest.raises(ValueError):
        ModelOption(slug="a", label="A", efforts=["low"], colour="red")                      # type: ignore[call-arg]
    with pytest.raises(ValueError):
        ModelOption(slug="a", label="A", efforts=["ultra"])                                  # type: ignore[list-item]


class Listing:
    def __init__(self, rows=(), boom=False):
        self.rows, self.boom = rows, boom

    def models(self):
        if self.boom:
            raise ConnectorError("cannot ask")
        return list(self.rows)


class Row:
    def __init__(self, slug, efforts, window=None):
        self.slug, self.label, self.efforts, self.context_window = slug, slug.upper(), efforts, window


def test_codex_options_come_from_what_codex_lists_with_its_own_efforts():
    options = options_for("codex", Listing([Row("gpt-5.6-luna", ["low", "medium"], 258_400)]))
    assert [(o.slug, o.label, o.efforts, o.context_window, o.group) for o in options] == [("gpt-5.6-luna", "GPT-5.6-LUNA", ["low", "medium"], 258_400, "main")]


def test_a_provider_that_cannot_be_asked_offers_nothing_instead_of_failing():
    assert options_for("codex", Listing(boom=True)) == []
    assert options_for("claude", Listing(boom=True)) == claude_options()                    # Claude's table is its own: the connector is not asked


def test_the_refusal_lists_the_valid_names_and_cuts_a_long_list():
    assert names_of(claude_options(), limit=3) == "best, opus, sonnet and 8 more"
    assert names_of(claude_options()[:2]) == "best, opus"
