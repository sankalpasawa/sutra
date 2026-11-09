"""The agent choices file (D131): the shape both sides share, the atomic private write, and the engine's cheap, forgiving reader."""
from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from sutra_app.connectors.agent_picks import CHOICES_FILE, SCHEMA, AgentPicks, build_choices, write_choices
from sutra_app.connectors.models import Pick
from sutra_app.engine.port import CallTag


def tag(fn):
    return CallTag(function=fn)


def test_the_body_holds_only_agents_that_chose_and_says_where_the_default_came_from():
    body = build_choices(7, Pick(provider="claude", model="sonnet", effort="high"), {
        "identity": Pick(provider="codex", model="gpt-5.6-luna", effort="medium"), "W-3": Pick(provider="claude", model="haiku", effort="low"),
        "audit": Pick(provider="")}, default_from="run")
    assert body == {"schema": SCHEMA, "rev": 7, "default": {"provider": "claude", "model": "sonnet", "effort": "high", "from": "run"},
                    "agents": {"W-3": {"provider": "claude", "model": "haiku", "effort": "low"},
                               "identity": {"provider": "codex", "model": "gpt-5.6-luna", "effort": "medium"}}}
    assert build_choices(1, None, {})["default"] is None


def test_an_identical_body_is_not_written_twice_and_the_file_is_private(tmp_path):
    path = tmp_path / CHOICES_FILE
    body = build_choices(1, None, {"identity": Pick(provider="claude", model="haiku", effort="low")})
    assert write_choices(path, body) is True
    assert write_choices(path, {**body, "rev": 2}) is False                               # only the rev differs
    assert write_choices(path, build_choices(3, None, {"identity": Pick(provider="claude", model="sonnet")})) is True
    assert json.loads(path.read_text(encoding="utf-8"))["rev"] == 3
    assert [p.name for p in tmp_path.iterdir()] == [CHOICES_FILE]                          # no temporary file is left
    if not sys.platform.startswith("win"):
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_the_reader_gives_the_agents_own_pick_then_the_default_then_none(tmp_path):
    path = tmp_path / CHOICES_FILE
    reader = AgentPicks(path)
    assert reader.for_tag(tag("identity")) is None                                         # no file: nobody chose
    write_choices(path, build_choices(1, Pick(provider="claude", model="sonnet", effort="high"), {"W-3": Pick(provider="codex", model="gpt-5.6-luna")}))
    assert reader.for_tag(tag("W-3")) == Pick(provider="codex", model="gpt-5.6-luna")
    assert reader.for_tag(tag("identity")) == Pick(provider="claude", model="sonnet", effort="high")


def test_a_change_applies_at_the_next_call_and_a_removed_choice_falls_back(tmp_path):
    path = tmp_path / CHOICES_FILE
    reader = AgentPicks(path)
    write_choices(path, build_choices(1, None, {"identity": Pick(provider="claude", model="haiku", effort="low")}))
    assert reader.for_tag(tag("identity")).model == "haiku"
    write_choices(path, build_choices(2, None, {"identity": Pick(provider="claude", model="sonnet", effort="high")}))
    assert reader.for_tag(tag("identity")).model == "sonnet"
    write_choices(path, build_choices(3, None, {}))
    assert reader.for_tag(tag("identity")) is None


@pytest.mark.parametrize("text", ["not json", "[]", '{"schema": "other/9"}', '{"schema": "agent-choices/1", "agents": []}',
                                  '{"schema": "agent-choices/1", "agents": {"identity": {"provider": "claude", "effort": "wild"}}}'])
def test_a_file_that_cannot_be_used_is_ignored_and_never_raises(tmp_path, text, caplog):
    path = tmp_path / CHOICES_FILE
    path.write_text(text, encoding="utf-8")
    reader = AgentPicks(path)
    assert reader.for_tag(tag("identity")) is None and reader.for_tag(tag("W-1")) is None
    assert len([r for r in caplog.records if "is not used" in r.message]) == 1               # said once, not on every call
