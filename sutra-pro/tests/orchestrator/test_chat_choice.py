"""One choice for every surface (work package ABS-8): the pill governs the org chat agent and each team's run."""
from __future__ import annotations

import sys

import pytest
from orchestrator.test_tasks import tenv  # noqa: F401  (fixture)

from sutra_app.connectors.models import ConnectorConfig, JsonRequest, RouteContext
from sutra_app.connectors.router import Router
from sutra_app.orchestrator.chat_v2 import ChatChoices
from sutra_app.orchestrator.models import RunSpec
from connectors.test_router_chat import Named, policy


def build(tmp_path, choices):
    cfg = ConnectorConfig(data_dir=tmp_path / "d", work_root=tmp_path / "w", claude_exe=sys.executable, codex_exe=sys.executable)
    claude, codex = Named("claude", cfg), Named("codex", cfg)
    events = []
    router = Router({"claude": claude, "codex": codex}, policy(), events=lambda t, d: events.append((t, d)), sleep=lambda s: None, rng=lambda: 0.0)
    router.choice_source = choices.get
    return router, claude, codex, events


class Choices(dict):
    def get(self, sid, default=None):
        return dict.get(self, sid, default)


def ask(router, session="cs_org"):
    try:
        router.call_json(JsonRequest(user="plan", schema={"type": "object"}, ctx=RouteContext(session_id=session)))
    except Exception:
        pass                                              # the stub's reply need not be JSON; where the prompt went is what is checked


def test_the_org_chat_follows_its_chats_choice(tmp_path):
    router, claude, codex, _ = build(tmp_path, Choices({"cs_org": "codex"}))
    ask(router)
    assert codex.calls and not claude.calls


def test_another_session_and_no_choice_keep_the_policy_order(tmp_path):
    router, claude, codex, _ = build(tmp_path, Choices({"cs_org": "codex"}))
    ask(router, "cs_aaaaaaaaaaaa")
    assert claude.calls and not codex.calls


def test_clearing_the_choice_restores_the_policy(tmp_path):
    choices = Choices({"cs_org": "codex"})
    router, claude, codex, _ = build(tmp_path, choices)
    ask(router)
    choices.clear()
    seen = len(codex.calls)
    ask(router)
    assert len(claude.calls) == 1 and len(codex.calls) == seen


def test_a_choice_that_cannot_run_falls_back_to_the_policy_and_says_so(tmp_path):
    router, claude, codex, events = build(tmp_path, Choices({"cs_org": "codex"}))
    router.policy.providers["codex"].enabled = False
    ask(router)
    assert claude.calls
    note, = [d for t, d in events if t == "connector.choice_unavailable"]
    assert note["wanted"] == "codex" and note["used"] == "claude" and "disabled" in note["reason"]


def test_a_broken_choice_source_never_breaks_a_call(tmp_path):
    router, claude, codex, _ = build(tmp_path, Choices())
    router.choice_source = lambda sid: 1 / 0
    ask(router)
    assert claude.calls


def test_a_run_started_after_a_choice_carries_it(tenv):  # noqa: F811
    sid = tenv.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'")
    with tenv.db.tx() as tx:
        ChatChoices(tenv.db).set(tx, sid, "codex")
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    assert RunSpec.model_validate_json((tenv.run_dir(task.id) / "task.json").read_text()).connector == "codex"


def test_without_a_choice_a_run_keeps_the_settings_connector_and_clearing_restores_it(tenv):  # noqa: F811
    sid = tenv.one("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'")
    with tenv.db.tx() as tx:
        ChatChoices(tenv.db).set(tx, sid, "codex")
        ChatChoices(tenv.db).set(tx, sid, None)
    task = tenv.new()
    tenv.run(tenv.service.start_ready())
    assert RunSpec.model_validate_json((tenv.run_dir(task.id) / "task.json").read_text()).connector == "auto"
