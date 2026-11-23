"""The Work list, tags and "How did it go?" (DV-2, SUTRA_WORK_V1): with the switch off nothing of it exists (no route, no table read); with it on one list holds tasks and, with the nodes, projects; tags are
the owner's plain words and refuse a secret; the summary is computed by code from rows and says in plain words what a project cost and where it got stuck."""
import json

import pytest
from fastapi.testclient import TestClient
from orchestrator.projects_rig import PRig  # noqa: F401
from orchestrator.test_projects_adopt import BASE, HEADERS, make_app

from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.work import TAG_MAX, TAGS_PER_ITEM, WorkService, clean_tags

T0 = 1793786400


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=6, max_live=12)


def service(rig, projects=False):
    return WorkService(rig.t.db, redact=lambda text: text.replace("hunter2hunter2", "[redacted]"), projects=projects)


# ---- the switch off ---------------------------------------------------------------------------------------------------------------------
def test_with_the_switch_off_there_is_no_work_route_before_or_after_the_token(tmp_path):
    app, _connector = make_app(tmp_path)
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not [p for p in paths if p.startswith("/api/work") or p.endswith("/summary") or p == "/work"]                      # the routes do not exist: the route table is what it was
    with TestClient(app, base_url=BASE) as client:
        for method, url in (("get", "/api/work"), ("get", "/api/work/tags"), ("get", "/api/projects/prj_000000000000/summary"), ("get", "/work")):
            assert getattr(client, method)(url).status_code == 404, url
        for headers in ({}, HEADERS):
            assert client.put("/api/work/task/tsk_000000000001/tags", json={"tags": ["x"]}, headers=headers).status_code == 404      # 404 for everybody, token or none
        assert app.state.services.db.conn().execute("SELECT count(*) FROM work_tags").fetchone()[0] == 0


# ---- tags ---------------------------------------------------------------------------------------------------------------------------
def test_a_tag_is_a_plain_lower_case_word_and_anything_else_is_refused_in_plain_words():
    assert clean_tags(["  Cafe  Menu ", "weekly", "cafe menu"]) == ["cafe menu", "weekly"]                                    # case folded, spaces collapsed, no duplicate, sorted
    for bad in (["x" * (TAG_MAX + 1)], [""], ["   "], ["bad/tag"], ["<b>"], ["tag!"], [5], "nope", [["x"]], [str(i) for i in range(TAGS_PER_ITEM + 1)]):
        with pytest.raises(AppError) as refused:
            clean_tags(bad)
        assert refused.value.code == "validation" and refused.value.message
    with pytest.raises(AppError) as secret:
        clean_tags(["hunter2hunter2"], redact=lambda text: text.replace("hunter2hunter2", "[redacted]"))
    assert "key, a token or a password" in secret.value.message and "hunter2" not in secret.value.message             # never echoed
    with pytest.raises(AppError):
        clean_tags(["ghp_" + "a" * 36])                                                                                  # the shape of a credential is refused too


def test_tags_are_replaced_as_a_set_and_only_for_an_item_that_exists(rig):
    task = rig.t.new("web", "A page for my cafe").id
    work = service(rig)
    assert work.set_tags("task", task, ["cafe", "weekly"]) == ["cafe", "weekly"]
    assert work.set_tags("task", task, ["cafe"]) == ["cafe"] and [t["tag"] for t in work.all_tags()] == ["cafe"]
    assert work.set_tags("task", task, []) == [] and work.all_tags() == []
    with pytest.raises(NotFound):
        work.set_tags("task", "tsk_000000000999", ["x"])
    with pytest.raises(NotFound):
        work.set_tags("project", "prj_000000000999", ["x"])                                                               # projects only with the nodes on
    with pytest.raises(NotFound):
        work.set_tags("chat", task, ["x"])


# ---- the list -----------------------------------------------------------------------------------------------------------------------
def test_the_list_is_newest_first_and_filters_by_tag_words_and_status(rig):
    first = rig.t.new("web", "Write the menu for my cafe").id
    rig.sql("UPDATE tasks SET created_at = ? WHERE id = ?", T0 - 500, first)
    second = rig.t.new("sales", "Quote for the wedding").id
    work = service(rig)
    work.set_tags("task", first, ["cafe"])
    assert [i["id"] for i in work.items()] == [second, first]
    assert [i["id"] for i in work.items(tag="Cafe")] == [first] and work.items(tag="nothing") == []
    assert [i["id"] for i in work.items(q="MENU cafe")] == [first] and [i["id"] for i in work.items(q="wedding")] == [second] and work.items(q="menu wedding") == []
    assert [i["id"] for i in work.items(status="queued")] == [second, first] and work.items(status="done") == []
    row = work.items(q="menu")[0]
    assert row["kind"] == "task" and row["status_word"] and row["tags"] == ["cafe"] and row["link"].startswith("/d/") and row["created_at"].endswith("Z")
    assert len(work.items(limit=1)) == 1 and work.items(limit=1, offset=1)[0]["id"] == first and work.items(offset=5) == []


def test_a_step_of_a_project_is_listed_under_its_project_not_on_its_own_and_projects_need_the_nodes(rig):
    plain = rig.t.new("ops", "A plain task").id
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], title="Cafe site")
    off, on = service(rig, projects=False), service(rig, projects=True)
    assert {i["id"] for i in on.items()} == {plain, reservation.project_id}
    project = [i for i in on.items() if i["kind"] == "project"][0]
    assert project["title"] == "Cafe site" and project["link"] == f"/p/{reservation.project_id}" and project["status_word"]
    assert reservation.project_id not in {i["id"] for i in off.items()}
    on.set_tags("project", reservation.project_id, ["cafe"])
    assert [i["id"] for i in on.items(tag="cafe")] == [reservation.project_id]


# ---- how did it go ------------------------------------------------------------------------------------------------------------------
def test_the_summary_says_what_it_used_what_was_tried_again_what_was_asked_and_where_it_got_stuck(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], title="Cafe site")
    pid = reservation.project_id
    rig.sql("UPDATE projects SET caps_json = json_set(caps_json, '$.retries', 1)")
    rig.start()
    rig.go(tasks["a1"])
    for _ in range(3):
        rig.sql("INSERT INTO usage_ledger(at, provider, purpose, task_id, usd) VALUES (?, 'claude', 'agent_turn', ?, 0.2)", T0, tasks["a1"])
    rig.finish(tasks["a1"], status="crashed", outcome="it crashed", handoff=False)                                         # tried again once
    summary = service(rig, projects=True).summary(pid)
    assert summary["calls"] == 3 and summary["usd"] == pytest.approx(0.6) and summary["retries"] == 1
    assert summary["lines"][0] == "It is still going." and "It used 3 credits and about $0.60" in summary["lines"][1]
    assert any("a1 was tried again after a failure (1 extra try)" in line for line in summary["lines"])
    names = {s["name"]: s for s in summary["steps"]}                                                                       # a step is named by its task's title (here the rig gives the ref)
    assert names["a1"]["tries"] == 2 and names["a1"]["calls"] == 3 and names["a2"]["calls"] == 0 and names["a2"]["usd"] is None and names["a1"]["usd"] == pytest.approx(0.6)
    assert names["a1"]["state_word"] and names["a2"]["state_word"] == "Waiting for another step" or names["a2"]["state_word"]      # node states have owner words from the server
    assert summary["minutes"] is not None                                                                                  # after a retry the first attempt's start still counts


def test_the_summary_of_an_ended_project_names_the_question_the_notice_and_the_reason(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], title="Cafe site", needs={"a2": ("github",)})
    pid = reservation.project_id
    [asked] = rig.store.approvals(pid, status="open")
    rig.t.run(rig.projects.answer(pid, asked.id, "deny"))                                                                  # a no to one step's question
    with rig.t.db.tx() as tx:
        rig.store.audit(tx, actor="conductor", action="scope.unchecked", project_id=pid, decision="n/a", reason="git could not say")
    rig.t.run(rig.projects.stop(pid))
    summary = service(rig, projects=True).summary(pid)
    lines = " | ".join(summary["lines"])
    assert summary["status"] == "stopped" and summary["questions"] == 1 and summary["scope_notices"] == 1
    assert "It stopped." in lines and "You were asked 1 question." in lines and "Sutra could not check which files a step changed (1 time)." in lines and "Why:" in lines
    assert not any(word in lines.lower() for word in ("node", "lease", "tier", "grant", "ledger", "ceiling"))
    with pytest.raises(NotFound):
        service(rig, projects=False).summary(pid)                                                                          # without the nodes there are no projects
    with pytest.raises(NotFound):
        service(rig, projects=True).summary("prj_000000000999")


# ---- the routes with the switch on ----------------------------------------------------------------------------------------------------
def test_with_the_switch_on_the_routes_answer_a_write_needs_the_token_and_a_bad_body_is_refused(tmp_path):
    from orchestrator.test_project_page_route import one_project
    app, connector = make_app(tmp_path, work_v1=True)
    client = one_project(app, connector)                                                                                 # a request that made two ordinary tasks (the nodes are off)
    try:
        items = client.get("/api/work").json()
        assert len(items) == 2 and all(i["kind"] == "task" and i["tags"] == [] for i in items)
        task = items[0]["id"]
        assert client.put(f"/api/work/task/{task}/tags", json={"tags": ["cafe"]}).status_code == 401
        assert client.put(f"/api/work/task/{task}/tags", json={"tags": ["cafe"], "extra": 1}, headers=HEADERS).status_code == 422
        assert client.put(f"/api/work/task/{task}/tags", json={"tags": ["bad/tag"]}, headers=HEADERS).status_code == 422
        assert client.put(f"/api/work/chat/{task}/tags", json={"tags": ["x"]}, headers=HEADERS).status_code == 422
        assert client.put("/api/work/task/tsk_000000000999/tags", json={"tags": ["x"]}, headers=HEADERS).status_code == 404
        assert client.put(f"/api/work/task/{task}/tags", json={"tags": ["Cafe", "weekly"]}, headers=HEADERS).json() == {"tags": ["cafe", "weekly"]}
        assert [i["id"] for i in client.get("/api/work?tag=cafe").json()] == [task] and client.get("/api/work/tags").json() == [{"tag": "cafe", "count": 1}, {"tag": "weekly", "count": 1}]
        assert client.get("/api/work?q=zzzz").json() == [] and client.get("/api/work?limit=0").status_code == 422
        assert client.get("/api/projects/prj_000000000001/summary").status_code == 404                                       # needs the nodes too
    finally:
        client.__exit__(None, None, None)


def test_the_work_page_exists_only_with_the_switch_on_and_every_file_it_names_is_served(tmp_path):
    import re
    off, _c = make_app(tmp_path / "off")
    with TestClient(off, base_url=BASE) as client:
        assert client.get("/work").status_code == 404
        home = client.get("/")
        assert "/work" not in home.text and "work_page" not in home.text
    on, _c = make_app(tmp_path / "on", work_v1=True)
    with TestClient(on, base_url=BASE) as client:
        page = client.get("/work")
        assert page.status_code == 200 and 'id="work-root"' in page.text and '"page":"work"' in page.text and "<!--SUTRA-BOOT-->" not in page.text
        assert client.head("/work").status_code == 200
        for name in re.findall(r'(?:src|href)="(/ui/[^"]+)"', page.text):
            assert client.get(name).status_code == 200, name


# ---- review findings ---------------------------------------------------------------------------------------------------------------------
def test_every_attempt_of_a_retried_step_is_under_its_project_not_listed_on_its_own(rig):                         # review 1
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], title="Cafe site")
    rig.start()
    rig.go(tasks["a1"])
    rig.finish(tasks["a1"], status="crashed", outcome="it crashed", handoff=False)                                         # the first attempt ends and a second is made
    new = rig.sql("SELECT task_id FROM agent_nodes WHERE plan_ref = 'a1'").fetchone()[0]
    assert new != tasks["a1"] and rig.t.status(tasks["a1"]) == "crashed"
    work = service(rig, projects=True)
    assert [i["kind"] for i in work.items()] == ["project"]                                                                # no "a1 - Did not finish" next to the project
    assert work.items(status="crashed") == [] and work.items(q="a1") == []
    assert {i["kind"] for i in service(rig, projects=False).items()} == {"task"}                                           # without the nodes there are no projects: the tasks are what there is


def test_a_secret_in_capitals_is_refused_as_typed_and_nothing_is_echoed_back():                                          # review 3
    for secret in ("AKIAIOSFODNN7EXAMPLE", "password=hunter2hunter2", "ghp_" + "A" * 36):
        with pytest.raises(AppError) as refused:
            clean_tags([secret])
        assert refused.value.code == "validation" and secret not in refused.value.message and secret.lower() not in refused.value.message.lower()
    with pytest.raises(AppError) as plain:
        clean_tags(["bad/tag with 'quotes'"])
    assert "bad/tag" not in plain.value.message and "1 to 30 letters" in plain.value.message                              # a tag that is only badly spelled is not repeated either
    assert clean_tags(["Café", "CAFE 2"]) == ["cafe 2", "café"]                                                            # capitals and accents in an ordinary word are fine


def test_a_tag_with_a_hidden_character_is_refused_and_one_with_a_joiner_for_a_language_is_not():                          # review 4
    for hidden in ("ca\u200bfe", "ca\u202efe", "cafe\U000e0041", "cafe\ue000", "\u2060cafe", "cafe\ufeff"):
        with pytest.raises(AppError) as refused:
            clean_tags([hidden])
        assert "hidden character" in refused.value.message
    assert clean_tags(["ca\u200dfe"]) == ["ca\u200dfe"]                                                                    # the joiner some languages and emoji need is kept


def test_the_list_is_filtered_and_paged_by_the_database_and_its_limit_is_a_page(rig):                                   # review 10, 11
    for i in range(7):
        rig.sql("INSERT INTO usage_ledger(at, provider, purpose, task_id, usd) SELECT ?, 'claude', 'x', id, 0.1 FROM tasks LIMIT 0", T0)
        task = rig.t.new("web", f"Write note number {i} about the 100% real menu_v2")
        rig.sql("UPDATE tasks SET created_at = ? WHERE id = ?", T0 - i * 10, task.id)
    work = service(rig)
    assert [i["title"] for i in work.items(limit=3)] and len(work.items(limit=3)) == 3 and len(work.items(limit=3, offset=3)) == 3 and len(work.items(limit=3, offset=6)) == 1
    assert len(work.items(q="100% real")) == 7 and work.items(q="100%x") == [] and len(work.items(q="menu_v2")) == 7 and work.items(q="menu_v3") == []        # % and _ are letters, not patterns
    assert len(work.items(q="NOTE number 3")) == 1


def test_home_gets_a_row_for_a_page_only_while_its_switch_is_on_and_with_both_off_it_is_the_file_as_it_was(tmp_path):          # architect ruling (DV-2b)
    import re
    bodies = {}
    for name, flags in (("off", {}), ("work", {"work_v1": True}), ("recipes", {"recipes_v1": True}), ("both", {"work_v1": True, "recipes_v1": True})):
        app, _c = make_app(tmp_path / name, **flags)
        with TestClient(app, base_url=BASE) as client:
            bodies[name] = client.get("/").text
    row = lambda ident: re.search(rf'\n    <a class="railteam" href="/[a-z]+" id="{ident}">.*?</a>', bodies["both"])                    # noqa: E731
    assert "/work" not in bodies["off"] and "/recipes" not in bodies["off"]
    assert 'id="gowork"' in bodies["work"] and 'id="gorecipes"' not in bodies["work"] and 'id="gorecipes"' in bodies["recipes"] and 'id="gowork"' not in bodies["recipes"]
    stripped = bodies["both"]
    for ident in ("gowork", "gorecipes"):
        stripped = stripped.replace(row(ident).group(0), "")
    assert stripped == bodies["off"]                                                                                           # take the two rows away and the page is byte for byte the flag-off page
    assert '<span class="rtname">Work</span>' in bodies["both"] and '<span class="rtname">Recipes</span>' in bodies["both"]
