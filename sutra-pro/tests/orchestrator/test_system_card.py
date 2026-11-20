"""The system permission gate (MAN-15, D295, D296): a step that needs a permission of the computer waits in `awaiting_system` with ONE card; the steps it does not affect run; "Check again" lets the
affected ones go on; "Skip" cancels only them; Decide for me cannot answer it; a sleeping computer or a closed app refuses it like any gate. Fake adapters: no real system dialog."""
import json

import pytest
from orchestrator.projects_rig import PRig  # noqa: F401

from sutra_app.orchestrator.nodes_store import GATE_REFUSED_SLEEP
from sutra_app.syspermissions import MacAdapter, Need, WindowsAdapter

BASE = 1793786400


class FakeMac(MacAdapter):
    """macOS words and steps; the probe says what the test says."""

    def __init__(self, tmp_path, blocked=True):
        super().__init__(home=tmp_path)
        self.blocked, self.probes = blocked, []

    def probe(self, folder, *, write):
        self.probes.append((str(folder), write))
        return [Need("files_folders", "write", "Desktop")] if (self.blocked and write) else []


@pytest.fixture
def rig(db, settings, clock, events, tmp_path):
    rig = PRig(db, settings, clock, events, max_runs=5, max_live=10)
    rig.projects._folder_of = lambda: str(tmp_path / "work")
    rig.projects._output_of = lambda dept: "edit" if dept == "web" else "read"                   # `web` writes in the folder, the others only read it
    rig.adapter = rig.projects._adapter = FakeMac(tmp_path)
    return rig


def system_questions(rig, project_id):
    return [a for a in rig.store.approvals(project_id) if a.request.get("kind") == "system"]


def test_only_the_steps_the_permission_affects_wait_and_the_others_run(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    states = rig.node_states(tasks)
    assert states["a1"] == "awaiting_system" and states["a2"] in ("planned", "queued")
    [question] = system_questions(rig, reservation.project_id)
    assert question.tier == 2 and question.request["item"] == "files_folders" and question.request["nodes"] == [rig.node_of(tasks["a1"])["id"]]
    started = rig.start()
    assert started == [tasks["a2"]] and "Waiting for your answer" in rig.detail(tasks["a1"])
    assert [r["action"] for r in rig.audit("system.asked")] == ["system.asked"]


def test_a_plan_whose_steps_only_read_asks_the_read_question_not_the_write_one_and_a_free_computer_asks_nothing(rig):
    rig.projects._output_of = lambda dept: "read"
    assert rig.adapter.probes == []
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    assert system_questions(rig, reservation.project_id) == [] and rig.adapter.probes == [(rig.adapter.probes[0][0], False)]            # one read probe, no write probe
    rig.adapter.blocked = False
    rig.projects._output_of = lambda dept: "edit"
    other, more = rig.request([("b1", "dev", []), ("b2", "legal", [])], request_id="req-2", probe=True)
    assert system_questions(rig, other.project_id) == [] and set(rig.node_states(more).values()) <= {"planned", "queued"}


def test_check_again_with_the_permission_given_moves_the_waiting_steps_on_and_they_start(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    rig.adapter.blocked = False                                                                         # the owner allowed it in the settings
    snapshot = rig.t.run(rig.projects.system_check(reservation.project_id, "files_folders"))
    assert snapshot["system_cards"] == [] and rig.node_states(tasks)["a1"] in ("queued", "leased") and [a.status for a in system_questions(rig, reservation.project_id)] == ["allowed_once"]
    assert rig.t.status(tasks["a1"]) in ("starting", "running", "queued") and [r["action"] for r in rig.audit("system.cleared")] == ["system.cleared"]
    assert {s.task_id for s, *_ in rig.t.launcher.started} >= {tasks["a1"]}


def test_check_again_when_it_is_still_blocked_keeps_the_card_and_says_so(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    snapshot = rig.t.run(rig.projects.system_check(reservation.project_id, "files_folders"))
    assert len(snapshot["system_cards"]) == 1 and rig.node_states(tasks)["a1"] == "awaiting_system" and [r["action"] for r in rig.audit("system.still_needed")] == ["system.still_needed"]


def test_skip_cancels_only_the_steps_that_need_it_and_the_project_goes_on(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    snapshot = rig.t.run(rig.projects.system_skip(reservation.project_id, "files_folders"))
    assert rig.node_states(tasks)["a1"] == "cancelled" and rig.t.status(tasks["a1"]) == "cancelled" and "skipped" in rig.t.row(tasks["a1"]).outcome
    assert snapshot["project"]["status"] == "running" and rig.node_states(tasks)["a2"] in ("queued", "leased") and [a.status for a in system_questions(rig, reservation.project_id)] == ["denied"]
    assert [r["action"] for r in rig.audit("system.skipped")] == ["system.skipped"] and rig.t.status(tasks["a2"]) in ("starting", "running", "queued")


def test_decide_for_me_does_not_answer_a_permission_of_the_computer(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], decide_for_me=True, probe=True)
    [question] = system_questions(rig, reservation.project_id)
    assert question.status == "open" and rig.audit("gate.decided") == [] and rig.node_states(tasks)["a1"] == "awaiting_system"


def test_the_card_has_the_mac_steps_on_macos_and_the_windows_steps_on_windows(rig, tmp_path):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    [mac] = rig.projects.system_cards(reservation.project_id)
    assert mac.platform == "macos" and any("Files & Folders" in step for step in mac.steps) and mac.item == "files_folders" and mac.options == ["check_again", "skip"]

    class FakeWindows(WindowsAdapter):
        def probe(self, folder, *, write):
            return [Need("controlled_folder", "write", "work")] if write else []
    rig.projects._adapter = FakeWindows()
    other, more = rig.request([("b1", "web", []), ("b2", "sales", [])], request_id="req-2", probe=True)
    [windows] = rig.projects.system_cards(other.project_id)
    assert windows.platform == "windows" and any("Controlled folder access" in step for step in windows.steps) and not any("Files & Folders" in step for step in windows.steps)
    assert json.dumps(windows.model_dump(mode="json")) and rig.t.run(rig.projects.system_check(other.project_id, "controlled_folder"))["system_cards"]


def test_an_open_permission_question_is_refused_by_a_sleep_like_any_gate(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    rig.start()
    rig.go(tasks["a2"])
    rig.t.run(rig.projects.tick(now=BASE + 10))
    done = rig.t.run(rig.projects.tick(now=BASE + 3000))
    assert done["refused"] == [reservation.project_id] and rig.project(reservation.project_id)["stop_reason"] == GATE_REFUSED_SLEEP
    assert [a.status for a in system_questions(rig, reservation.project_id)] == ["denied"] and set(rig.node_states(tasks).values()) == {"cancelled"}


def test_the_probe_is_not_run_inside_the_task_gate_and_the_gate_only_reads_the_node_state(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    before = len(rig.adapter.probes)
    for _ in range(3):
        rig.start()
    assert len(rig.adapter.probes) == before                                                           # starting things never probes


# ---- the probe has a time limit, and a stopped project makes no task (G16, D322) ----------------------------------------------------------

def test_a_probe_that_never_returns_ends_in_a_card_after_the_time_limit(rig, monkeypatch):
    import threading
    from sutra_app.orchestrator import projects
    monkeypatch.setattr(projects, "PROBE_SECONDS", 0.2)
    release = threading.Event()

    class Hanging(FakeMac):
        def probe(self, folder, *, write):
            release.wait(5)
            return []
    rig.projects._adapter = Hanging(rig.projects._folder_of() and __import__("pathlib").Path("/tmp"))
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    release.set()
    questions = system_questions(rig, reservation.project_id)
    assert {q.request["item"] for q in questions} == {"unknown"} and {q.request["level"] for q in questions} == {"write", "read"}              # the write probe and the read probe both timed out
    assert rig.node_states(tasks) == {"a1": "awaiting_system", "a2": "awaiting_system"}


def test_a_project_stopped_between_the_reservation_and_its_tasks_makes_no_task(rig):
    from sutra_app.orchestrator.errors import AppError
    from sutra_app.orchestrator.projects import ProjectStep
    reservation = rig.projects.reserve("req-9", "t", [ProjectStep("a1", "web"), ProjectStep("a2", "sales")])
    rig.t.run(rig.projects.stop(reservation.project_id))
    before = rig.sql("SELECT count(*) FROM tasks").fetchone()[0]
    with pytest.raises(AppError):
        with rig.t.db.tx() as tx:
            task = rig.t.service.create(tx, dept_id="web", text="x", title="x", request="req-9")
            rig.projects.link_task(tx, reservation, "a1", task.id)
    assert rig.sql("SELECT count(*) FROM tasks").fetchone()[0] == before


def test_a_probe_that_raises_leaves_the_reserved_project_with_its_tasks(tmp_path):
    import time
    from fastapi.testclient import TestClient
    from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
    from orchestrator.test_projects_adopt import BASE as APP_BASE, NO_REQUESTS, make_app, rows, talk
    app, connector = make_app(tmp_path, nodes_v1=True)
    with TestClient(app, base_url=APP_BASE) as client:
        services = app.state.services

        async def boom(project_id):
            raise RuntimeError("the probe broke")
        services.projects.probe_system = boom
        talk(client, services, connector, "A page and a quote", decide(change="add", reuse=(), why="two"), change_reply(add_dept("$web", "Web", "Websites"), add_dept("$sales", "Sales", "Quotes")),
             assignments(draft("a1", "web", title="Page"), draft("a2", "sales", title="Quote")), NO_REQUESTS)
        assert len(rows(services, "SELECT * FROM tasks")) == 2 and len(rows(services, "SELECT * FROM projects")) == 1


# ---- the skip and the answer meet (M1) ------------------------------------------------------------------------------------------------------

def test_skipping_the_permission_and_then_answering_github_never_starts_the_step_the_skip_cancelled(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)}, probe=True)
    assert rig.node_states(tasks)["a1"] in ("awaiting_approval", "awaiting_system") and rig.node_states(tasks)["a2"] == "awaiting_approval"           # the plan's question holds both
    rig.t.run(rig.projects.system_skip(reservation.project_id, "files_folders"))
    assert rig.node_states(tasks)["a1"] == "cancelled" and rig.t.status(tasks["a1"]) == "cancelled"
    [github] = [a for a in rig.store.approvals(reservation.project_id, status="open") if a.request.get("kind") == "tier"]
    rig.t.run(rig.projects.answer(reservation.project_id, github.id, "allow_once"))
    started = {s.task_id for s, *_ in rig.t.launcher.started}
    assert tasks["a2"] in started and tasks["a1"] not in started and rig.node_states(tasks)["a1"] == "cancelled"


def test_answering_github_first_does_not_release_the_step_a_permission_question_still_names(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], needs={"a2": ("github",)}, probe=True)
    [github] = [a for a in rig.store.approvals(reservation.project_id, status="open") if a.request.get("kind") == "tier"]
    rig.t.run(rig.projects.answer(reservation.project_id, github.id, "allow_once"))
    started = {s.task_id for s, *_ in rig.t.launcher.started}
    assert tasks["a1"] not in started and rig.node_states(tasks)["a1"] in ("awaiting_approval", "awaiting_system")
    rig.adapter.blocked = False
    rig.t.run(rig.projects.system_check(reservation.project_id, "files_folders"))
    assert tasks["a1"] in {s.task_id for s, *_ in rig.t.launcher.started}


def test_the_permission_card_names_the_steps_it_holds_by_their_titles_not_by_ids(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    [card] = rig.projects.system_cards(reservation.project_id)
    assert card.affects == ["a1"] and not any(word.startswith("nd_") for word in card.affects)


def test_a_notice_of_the_adapter_is_one_plain_note_that_asks_nothing_and_blocks_nothing(rig):                    # R10
    class Noisy(FakeMac):
        def notices(self, folder):
            return ["Windows Controlled folder access is on. The steps run through the programs claude and codex."]
    rig.projects._adapter = Noisy(rig.adapter.home, blocked=False)
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", [])], probe=True)
    notes = rig.sql("SELECT text FROM chat_messages WHERE src_ref LIKE ?", f"project:{reservation.project_id}#system-notice%").fetchall()
    assert len(notes) == 1 and "claude and codex" in notes[0]["text"] and notes[0]["text"].endswith(f"/p/{reservation.project_id}")
    assert system_questions(rig, reservation.project_id) == [] and rig.node_states(tasks)["a1"] in ("planned", "queued")          # nothing is asked, nothing waits
