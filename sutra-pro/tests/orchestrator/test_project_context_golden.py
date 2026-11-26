"""D451, NFR-1 (a guard: it passes on 0.8.3 and must keep passing): a project with no files, no instructions and nothing remembered is given exactly what 0.8.3 gave it.

The run's framing, the chat's grounding and the router's carry-over are compared with samples stored in tests/fixtures/project_context. The samples were written by the code of origin/main at
e59d3ea0, before D451.
"""
from __future__ import annotations

import json
from pathlib import Path

from orchestrator.test_api_chat_v2 import H, rig, wait_for, world  # noqa: F401  (rig is a fixture)
from orchestrator.test_tasks import tenv  # noqa: F401  (a fixture)

from sutra_app.orchestrator.api import chat_v2
from sutra_app.orchestrator.models import RunSpec

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "project_context"


def golden(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


def test_a_run_of_a_project_with_nothing_has_the_framing_and_the_task_json_it_always_had(tenv):
    task = tenv.new("web", "Build a landing page for my cafe", framing="Earlier the team asked the owner: which colour?")
    tenv.run(tenv.service.start_ready())
    text = (tenv.run_dir(task.id) / "task.json").read_text()
    spec = json.loads(text)
    assert spec["framing"] == "Earlier the team asked the owner: which colour?" and "inputs" not in spec
    assert set(spec) == {"schema", "run_id", "task_id", "dept_id", "dept_label", "scope_id", "scope_label", "user_text", "framing", "parent_run_id", "seed_from", "upstream", "settings", "connector"}
    assert RunSpec.model_validate(spec).framing == spec["framing"]
    assert not (tenv.run_dir(task.id) / "inputs").exists()


def test_the_grounding_of_a_team_chat_with_nothing_is_the_text_it_always_was(rig):
    client, world, chats, bus, services = rig
    sid = world.session_of["web"]
    world.sql("UPDATE org_nodes SET purpose = ? WHERE id = ?", "Websites for the cafe", "web")
    assert client.post(f"/api/chats/{sid}/direct", json={"text": "what are you for?"}, headers=H).status_code == 202
    assert wait_for(lambda: len(chats.messages(sid)) == 2 and sid not in chat_v2._running)
    call = services.chat_port.router.connectors["stub"].calls[-1]
    assert call.system == golden("chat_system.txt").rstrip("\n") and call.prompt == "what are you for?"
