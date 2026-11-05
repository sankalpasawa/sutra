"""Scenario 3 (GAP-E2E, G05): the second request, and the follow-up after Done.

  "Also write a menu page." -> the chat agent REUSES the Web team (no chart change of substance) and a second task runs;
  a line written in the department chat after Done is a follow-up: a new task with `seed_from`, a new run folder and process,
  the old folder untouched, J2's change-request handling, Done again;
  a finished DOCUMENT CHAIN (PRD, HLD, LLD) is continued the same way (GAP-E1B is merged, so the 'falls back to fresh' of the
  first plan no longer applies to it; a refused source still does: a stopped run starts the next one fresh, with the old
  files as upstream and the fixed system line).

Everything runs the real engine process in J2's mock mode (see harness.py). Draw.io step 1 (reuse first) and step 6 (the graph
and the chats follow the engine) are the ones these tests lean on.
"""
import hashlib
import json
from pathlib import Path

import pytest
from harness import ANSWER, TERMINAL, LiveApp, decide, draft, new_team_script, run_new_team

from sutra_app.engine.rehydrate import continuing_line, fresh_line
from sutra_app.orchestrator.testing.scripted import ScriptedConnector

FOLLOW_UP = "Make the header darker please"
FACTS = (" Users: coffee lovers and office staff. Problem: people can't see the menu or order ahead. Must-have features: "
         "see the menu with prices, pre-order a coffee, find the shop, read the opening hours. Constraints: one page only. "
         "Success: 30 pre-orders per week.")
DOCS_ONLY = "Write the PRD, the HLD and the LLD for Brew Lab, a small specialty coffee shop's one-page ordering page." + FACTS
CHAIN_SETTINGS = {"J2_FIXES": "0", "J2_BUDGET": "900", "J2_MEMORY": "0"}          # what the engine's own chain tests use (QUIET)


def tree_sha(folder: Path) -> str:
    """One hash of every file below `folder` (names and bytes): 'the old folder was not written to'."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(folder)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def answer_when_asked(live: LiveApp, task: str, text: str, timeout: float = 60.0) -> None:
    live.until(f"{task} to ask", lambda: live.task_status(task) in ("waiting_user", *TERMINAL), timeout)
    if live.task_status(task) == "waiting_user":
        assert live.write(live.session_of("web"), text).status_code == 200


@pytest.fixture(scope="module")
def chain_of_tasks(tmp_path_factory):
    """Task 1 (new team) done; task 2 ('Also write a menu page.', reuse) done; task 3 (a follow-up line in the team's chat) done."""
    live = LiveApp(tmp_path_factory.mktemp("followup"), connector=ScriptedConnector()).start()
    try:
        first = run_new_team(live)
        calls_before = len(live.connector.calls)
        mid = live.say("Also write a menu page.", decide(change="reuse", reuse=("web",),
                                                        assignments=[draft("a1", "web", title="Menu page", brief="Write the menu page.")]))
        second = live.task_of_message(mid)
        answer_when_asked(live, second, ANSWER)
        live.ended(second)
        old_run = live.task_row(second)["run_id"]
        old_sha = tree_sha(live.run_dir(second))
        response = live.write(live.session_of("web"), FOLLOW_UP)
        assert response.status_code == 200, response.text
        third = response.json()["task_id"]
        live.until("the follow-up to ask", lambda: live.task_status(third) in ("waiting_user", *TERMINAL), 60)
        question = [m["text"] for m in live.messages(live.session_of("web")) if m["kind"] == "question"][-1]
        assert live.write(live.session_of("web"), "Option 2").status_code == 200           # the team asks 'keep going or finish as it is'
        live.ended(third)
        yield {"live": live, "first": first, "second": second, "third": third, "mid": mid, "calls_before": calls_before,
               "response": response.json(), "old_run": old_run, "old_sha": old_sha, "question": question}
    finally:
        try:
            live.stop()
        finally:
            live.kill_engines()


def test_step1_also_write_a_menu_page_reuses_the_team_and_runs_a_second_task(chain_of_tasks):
    c = chain_of_tasks
    live = c["live"]
    assert len(live.connector.calls) - c["calls_before"] == 1                                       # one decide call: reuse needs no chart stage
    reuse = live.rows("SELECT * FROM chart_changes ORDER BY seq DESC LIMIT 1")[0]
    assert (reuse["seq"], reuse["kind"], reuse["status"]) == (3, "reuse", "applied") and reuse["before_sha"] == reuse["after_sha"]
    assert live.one("SELECT count(*) FROM departments") == 1 and live.one("SELECT count(*) FROM org_nodes") == 2
    row = live.task_row(c["second"])
    assert (row["dept_id"], row["title"], row["status"], row["parent_task_id"]) == ("web", "Menu page", "done", None)
    assert row["run_id"] != live.task_row(c["first"].task)["run_id"] and row["settings_json"] == "{}"          # a fresh run: no seed
    assert [card["status"] for card in live.cards("task")][-1] in ("queued", "starting", "running", "done")
    assert len(live.cards("done")) >= 2


def test_step6_a_line_in_the_team_chat_after_done_is_a_follow_up_that_continues_the_last_run(chain_of_tasks):
    c = chain_of_tasks
    live = c["live"]
    assert c["response"]["delivered"] == "follow_up"
    row = live.task_row(c["third"])
    assert json.loads(row["settings_json"]) == {"_seed_from": c["old_run"]}                          # the reserved key of a follow-up
    assert row["parent_task_id"] == c["second"] and row["user_text"] == FOLLOW_UP and row["run_id"] not in (c["old_run"],)
    assert live.task_status(c["third"]) == "done"
    say = [e["text"] for e in live.events_of(c["third"]) if e["t"] == "say"]
    assert say[0] == continuing_line(c["old_run"]) and not any(t.startswith("Starting a new run") for t in say)
    assert say[0].startswith(f"Continuing from run {c['old_run']}: the team keeps its charter, workflows, findings and site")       # fixed wording
    team_chat = [m["text"] for m in live.messages(live.session_of("web"))]
    assert FOLLOW_UP in team_chat and "Keep going or finish as it is?" in c["question"]


def test_the_follow_up_run_holds_the_old_runs_files_and_the_old_folder_is_untouched(chain_of_tasks):
    c = chain_of_tasks
    live = c["live"]
    old, new = live.run_dir(c["second"]), live.run_dir(c["third"])
    assert tree_sha(old) == c["old_sha"]                                                             # read-only history
    old_goal, new_goal = (json.loads((folder / "goal.json").read_text()) for folder in (old, new))
    assert new_goal["statement"] == old_goal["statement"] and new_goal["done_when"] == old_goal["done_when"]       # the charter came along
    old_ids, new_ids = ([w["id"] for w in json.loads((folder / "workflows.json").read_text())] for folder in (old, new))
    assert new_ids[:len(old_ids)] == old_ids and old_ids
    assert (new / "style.json").read_bytes() == (old / "style.json").read_bytes()
    old_versions = sorted(p.name for p in (old / "site").iterdir())
    assert old_versions == sorted(p.name for p in (new / "site").iterdir()) and len(old_versions) >= 4
    for name in old_versions:
        assert (new / "site" / name).read_bytes() == (old / "site" / name).read_bytes(), name
    old_chat = (old / "chat.jsonl").read_text().splitlines()
    new_chat = (new / "chat.jsonl").read_text().splitlines()
    assert new_chat[1:len(old_chat)] == old_chat[1:] and len(new_chat) > len(old_chat)               # the transcript continues (header differs)
    summary = json.loads((new / "summary.json").read_text())
    assert summary["status"] == "done" and summary["change_requests"] == [FOLLOW_UP]
    assert live.task_row(c["third"])["pid"] != live.task_row(c["second"])["pid"]                     # a new process each time


def test_the_follow_up_ends_done_again_with_ledgers_for_every_run(chain_of_tasks):
    c = chain_of_tasks
    live = c["live"]
    assert [r["status"] for r in live.rows("SELECT status FROM tasks ORDER BY created_at")] == ["done"] * 3
    assert len(live.cards("done")) == 3
    assert live.one("SELECT count(*) FROM atoms WHERE display = 'open'") == 0
    assert live.one("SELECT count(*) FROM atom_ledger") == live.one("SELECT count(*) FROM atoms")
    per_task = {r["task_id"]: r["n"] for r in live.rows("SELECT task_id, count(*) n FROM usage_ledger WHERE task_id IS NOT NULL GROUP BY task_id")}
    for task in (c["first"].task, c["second"], c["third"]):
        events = [e for e in live.events_of(task) if e["t"] == "usage"]
        assert per_task[task] == len(events) > 0, task                                                # each run's calls, once
    assert live.one("SELECT count(*) FROM usage_ledger WHERE atom_id IS NULL") == 0
    assert live.one("SELECT state FROM graph_nodes WHERE id = 'web'") == "idle"


def test_step6_a_document_chain_follow_up_rehydrates_the_chain(tmp_path):
    with LiveApp(tmp_path, connector=ScriptedConnector(), extra_env={"J2_REALIZATION": "0"}) as live:
        live.add_department("docs", "Docs", "Product documents")
        response = live.post("/api/tasks", {"dept_id": "docs", "text": DOCS_ONLY, "settings": CHAIN_SETTINGS})
        assert response.status_code == 201, response.text
        first = response.json()["id"]
        live.ended(first)
        run = live.run_dir(first)
        assert {"documents.json", "stage-prd.json", "stage-hld.json", "stage-lld.json", "prd.md", "hld.md", "lld.md"} <= {p.name for p in run.iterdir()}
        sha = tree_sha(run)
        delivered = live.write(live.session_of("docs"), "make the HLD mention a CDN")
        assert delivered.status_code == 200 and delivered.json()["delivered"] == "follow_up"
        second = delivered.json()["task_id"]
        live.ended(second)
        say = [e["text"] for e in live.events_of(second) if e["t"] == "say"]
        old_run = live.task_row(first)["run_id"]
        assert say[0] == continuing_line(old_run) and not any(t.startswith("Starting a new run") for t in say)
        new = live.run_dir(second)
        for name in ("documents.json", "stage-prd.json", "stage-hld.json", "stage-lld.json", "prd.md", "hld.md", "lld.md"):
            assert (new / name).is_file(), name                                                      # the chain came along
        assert json.loads((new / "summary.json").read_text())["change_requests"] == ["make the HLD mention a CDN"]
        assert tree_sha(run) == sha and not (new / "upstream").exists()


def test_a_follow_up_after_a_stopped_run_starts_fresh_with_the_old_files_as_upstream(tmp_path):
    with LiveApp(tmp_path, connector=ScriptedConnector()) as live:
        mid = live.say("I need a landing page for my coffee shop", *new_team_script())
        first = live.task_of_message(mid)
        live.until("the question", lambda: live.task_status(first) == "waiting_user")
        stopped = live.post(f"/api/tasks/{first}/stop")
        assert stopped.status_code == 200 and stopped.json()["status"] == "stopped"
        old_run = live.task_row(first)["run_id"]
        delivered = live.write(live.session_of("web"), "Please start the page again")
        assert delivered.status_code == 200 and delivered.json()["delivered"] == "follow_up"
        second = delivered.json()["task_id"]
        live.until("the fresh run to speak", lambda: any(e["t"] == "say" for e in live.events_of(second)))
        line = [e["text"] for e in live.events_of(second) if e["t"] == "say"][0]
        assert line == fresh_line(old_run, "the earlier run was stopped before it finished")
        assert line.startswith(f"Starting a new run. Your earlier files from run {old_run} are in upstream/{old_run}/ for reference. Reason: ")
        assert json.loads(live.task_row(second)["settings_json"]) == {"_seed_from": old_run}          # asked to continue, refused, ran fresh
        assert live.task_row(second)["framing"].startswith("Earlier the team asked the owner: ")         # the question the stop left open
        assert (live.run_dir(second) / "upstream" / old_run).is_dir()                                   # the old files, for reference
        assert not any(e["t"] == "say" and e["text"].startswith("Continuing") for e in live.events_of(second))
