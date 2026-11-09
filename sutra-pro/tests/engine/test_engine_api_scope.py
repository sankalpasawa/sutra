"""Which team and which run a request is about (work package E4, engine design 7.2, S1-contracts-01, S3-web-12).

FastAPI `TestClient` over the `fake_services` fixture of conftest: J2's 28 data routes at the root with `?dept=`, the team named
nowhere else, the run named by `?run=` (saved, read-only) or found through `resolve_run` (live, else idle)."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.engine import views
from sutra_app.engine.api import MOUNT_MARK, build_router, ctx as ctxmod, mount
from sutra_app.engine.spec import EngineSettings

TOKEN = {"X-Sutra-Token": "fake-token-fake-token-0123"}
GET_PATHS = ["/api/state", "/api/runs", "/api/call?id=1", "/api/preview?atom=a", "/api/docs", "/api/map", "/api/plan", "/api/library",
             "/api/library/website/hero/main/v1", "/api/run-templates", "/api/artifacts", "/api/agent?who=identity",
             "/api/code?deck=a&section=b", "/api/artifacts/tree", "/api/artifact?name=x", "/api/story", "/api/board", "/api/audits",
             "/api/refs", "/shot/1", "/file/prd.md", "/site/latest", "/site/v1", "/api/runlist", "/api/changes"]
NOT_FOUND = {"/api/call?id=1", "/api/library/website/hero/main/v1", "/api/code?deck=a&section=b", "/api/artifact?name=x", "/shot/1",
             "/file/prd.md"}           # the view's own 404 for a run with nothing in it
POSTS = ["/api/say", "/api/playbooks/clear", "/api/lessons/clear", "/api/output", "/api/reset"]
BODIES = {"/api/say": {"text": "hello"}, "/api/output": {"type": "prd"}}


def join(path: str, query: str) -> str:
    return path + ("&" if "?" in path else "?") + query


def publish(svc, ref, *, status="waiting", pid=None, chat=(), sites=0, output="website"):
    """What the host writes for a live run: snapshot.json (what /api/state returns) and live.json."""
    folder = svc.data_dir / ref.dir
    memory = views.MemoryPaths(str(folder / "lessons"), str(folder / "playbooks"))
    snap = views.idle_snapshot(EngineSettings(), memory, ref.run_id)
    snap.update(status=status, chat=list(chat), total=len(chat), saved=None)
    (folder / "snapshot.json").write_text(json.dumps(snap), encoding="utf-8")
    live = {**views.EMPTY_LIVE, "pid": os.getpid() if pid is None else pid, "sites": sites, "output": output}
    (folder / "live.json").write_text(json.dumps(live), encoding="utf-8")


@pytest.fixture
def api(fake_services):
    svc = fake_services
    svc.add_department("web")
    svc.add_department("sales")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    mount(app, svc)
    return SimpleNamespace(svc=svc, app=app, client=TestClient(app, raise_server_exceptions=False), data=svc.data_dir)


def test_every_row_of_7_1_answers_at_the_root_with_dept_in_both_modes(api):
    ref = api.svc.add_run("web", files={"chat.jsonl": json.dumps({"meta": True, "run": "x", "output": "website"}) + "\n"})
    publish(api.svc, ref, chat=[{"id": 1, "who": "user", "text": "hi"}])
    for path in GET_PATHS:
        for query in ("dept=web", f"dept=web&run={ref.run_id}"):         # live (published files), then saved (the folder)
            got = api.client.get(join(path, query))
            assert got.status_code == (404 if path in NOT_FOUND else 200), (path, query, got.text[:200])


def test_the_route_table_is_the_28_j2_rows_plus_the_two_p13_routes_the_two_settings_routes_and_nothing_under_d(api):
    table = {(method.upper(), path) for path, item in api.app.openapi()["paths"].items() for method in item}
    gets = {"/api/state", "/api/runs", "/api/call", "/api/preview", "/api/docs", "/api/map", "/api/plan", "/api/library",
            "/api/library/{artifact}/{section}/{slug}/{version}", "/api/run-templates", "/api/artifacts", "/api/agent", "/api/code",
            "/api/artifacts/tree", "/api/artifact", "/api/story", "/api/board", "/api/audits", "/api/refs", "/shot/{n}",
            "/file/{name}", "/site/{key}",
            "/api/runlist", "/api/changes"}                      # 22 J2 paths: /site/{key} answers rows 24 and 25; the last two are P13
    assert table == {("GET", p) for p in gets} | {("POST", p) for p in POSTS} | {("GET", "/api/engine/settings"),
                                                                                  ("PUT", "/api/engine/settings"),
                                                                                  ("GET", "/api/engine/capabilities")}
    assert not [path for _, path in table if path.startswith("/d/")]


def test_without_a_valid_dept_every_route_answers_400_dept_required(api):
    for dept in ("", "?dept=", "?dept=Web", "?dept=a", "?dept=web/..", "?dept=web%0A", "?dept=_web", "?dept=web&dept=sales"):
        suffix = dept if dept.startswith("?") or not dept else "?" + dept
        for path in [p.split("?")[0] for p in GET_PATHS]:
            got = api.client.get(path.replace("{", "x").replace("}", "") + suffix)
            assert (got.status_code, got.json()) == (400, {"error": "dept_required"}), (path, dept, got.text[:100])
        for path in POSTS:
            got = api.client.post(path + suffix, json=BODIES.get(path, {}), headers=TOKEN)
            assert (got.status_code, got.json()) == (400, {"error": "dept_required"}), (path, dept)


def test_the_team_is_named_in_the_query_only_never_by_header_or_cookie(api):
    got = api.client.get("/api/state", headers={"X-Sutra-Dept": "web"}, cookies={"sutra_dept": "web"})
    assert got.status_code == 400
    assert api.client.get("/api/state?dept=web", headers={"X-Sutra-Dept": "sales"}).json()["status"] == "idle"


def test_an_unknown_department_is_404_not_found(api):
    for path in ("/api/state", "/api/refs", "/api/library", "/site/latest"):
        got = api.client.get(path + "?dept=nope")
        assert (got.status_code, got.json()) == (404, {"error": "not_found"})
    assert api.client.post("/api/say?dept=nope", json={"text": "x"}, headers=TOKEN).status_code == 404


def test_another_teams_run_and_a_malformed_run_id_are_404(api):
    other = api.svc.add_run("sales", files={"chat.jsonl": json.dumps({"meta": True}) + "\n"})
    api.svc.add_run("web")
    for path in ("/api/state", "/api/map", "/site/latest", "/api/docs"):
        assert api.client.get(join(path, f"dept=web&run={other.run_id}")).json() == {"error": "not_found"}
        assert api.client.get(join(path, f"dept=sales&run={other.run_id}")).status_code == 200
    for bad in ("../x", "j2-..%2f..", "j2-a/b", "nope", "j2-", "j2-x.y", "j2-unknown"):
        got = api.client.get("/api/state?dept=web&run=" + bad)
        assert (got.status_code, got.json()) == (404, {"error": "not_found"}), bad


def test_run_of_a_live_run_is_a_read_only_disk_view(api):
    ref = api.svc.add_run("web", status="running", files={"chat.jsonl": json.dumps({"meta": True}) + "\n" + json.dumps({"id": 1, "who": "user", "text": "disk"}) + "\n"})
    publish(api.svc, ref, status="running", chat=[{"id": 1, "who": "user", "text": "published"}])
    live = api.client.get("/api/state?dept=web").json()
    assert (live["status"], live["chat"][0]["text"], live["saved"]) == ("running", "published", None)
    assert (live["run_id"], live["dept_id"], live["host"]["alive"]) == (ref.run_id, "web", True)
    saved = api.client.get(f"/api/state?dept=web&run={ref.run_id}").json()
    assert (saved["saved"], saved["status"], saved["chat"][0]["text"]) == (ref.run_id, "saved", "disk")
    assert "host" not in saved
    assert api.client.get("/api/runs?dept=web").json()["live"] == ref.run_id


def test_a_dead_process_that_still_says_running_is_waiting_with_the_error(api):
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    ref = api.svc.add_run("web", status="running")
    publish(api.svc, ref, status="running", pid=gone.pid)
    state = api.client.get("/api/state?dept=web").json()
    assert (state["status"], state["error"], state["host"]["alive"]) == ("waiting", views.PROCESS_GONE, False)


def test_a_run_that_has_not_published_yet_shows_the_idle_page(api):
    api.svc.add_run("web", status="starting")                    # a folder with no snapshot.json: the host is still starting
    state = api.client.get("/api/state?dept=web").json()
    assert (state["status"], state["chat"], "run_id" in state) == ("idle", [], False)
    assert api.client.get("/api/map?dept=web").json()["live"] is False


def test_archived_department_reads_200_and_writes_403_read_only(api):
    api.svc.add_department("old", archived=True)
    ref = api.svc.add_run("old", files={"chat.jsonl": json.dumps({"meta": True}) + "\n"})
    assert api.client.get("/api/state?dept=old").status_code == 200
    assert api.client.get(f"/api/map?dept=old&run={ref.run_id}").status_code == 200
    for path in POSTS:
        got = api.client.post(path + "?dept=old", json=BODIES.get(path, {}), headers=TOKEN)
        assert got.status_code == 403, path
        assert got.json()["error"]["code"] == "read_only" and set(got.json()["error"]) == {"code", "message", "details"}
    assert api.svc.deliveries == [] and api.svc.stops == []


def test_after_a_reset_the_page_is_idle_until_the_next_task_but_history_stays(api):
    old = api.svc.add_run("web", files={"chat.jsonl": json.dumps({"meta": True}) + "\n" + json.dumps({"id": 1, "who": "user", "text": "x"}) + "\n"})
    publish(api.svc, old, chat=[{"id": 1, "who": "user", "text": "old"}])
    assert api.client.get("/api/state?dept=web").json()["chat"][0]["text"] == "old"
    assert api.client.post("/api/reset?dept=web", headers=TOKEN).status_code == 200
    state = api.client.get("/api/state?dept=web").json()
    assert (state["status"], state["chat"]) == ("idle", [])
    runs = api.client.get("/api/runs?dept=web").json()
    assert (runs["live"], [r["id"] for r in runs["runs"]]) == ("", [old.run_id])
    assert api.client.get(f"/api/state?dept=web&run={old.run_id}").json()["saved"] == old.run_id
    new = api.svc.add_run("web", run_id="j2-20261104-110000-ffff", status="running")           # the next task: newer than the marker
    publish(api.svc, new, status="running", chat=[{"id": 1, "who": "user", "text": "new"}])
    assert api.client.get("/api/state?dept=web").json()["chat"][0]["text"] == "new"


def test_the_idle_page_uses_the_departments_settings_files(api):
    (api.data / "departments" / "web" / "engine.json").write_text(json.dumps({"budget": 55, "output": "prd"}))
    state = api.client.get("/api/state?dept=web").json()
    assert (state["budget"], state["output"]) == (55, "prd")
    assert api.client.get("/api/state?dept=sales").json()["budget"] == EngineSettings().budget
    (api.data / "departments" / "web" / "engine.json").write_text("{not json")             # a broken file must not break the page
    assert api.client.get("/api/state?dept=web").json()["budget"] == EngineSettings().budget


def test_path_tricks_read_nothing_outside_the_run(api):
    api.svc.add_run("web", files={"secret.txt": "TOP SECRET", "prd.md": "# a"})
    (api.data / "outside.md").write_text("OUTSIDE")
    for path in ("/file/..%2f..%2f..%2f..%2foutside.md", "/file/%2e%2e/outside.md", "/shot/1%2f..%2f..", "/site/..%2f..",
                 "/api/artifact?name=../../../outside.md", "/api/artifact?name=/etc/passwd", "/api/code?deck=../x&section=y"):
        got = api.client.get(join(path, "dept=web"))
        assert got.status_code == 404 and "OUTSIDE" not in got.text and "SECRET" not in got.text, path


def test_a_run_folder_outside_the_teams_runs_is_not_read(api):
    (api.data / "elsewhere").mkdir()
    (api.data / "elsewhere" / "snapshot.json").write_text(json.dumps({"status": "running", "chat": []}))
    ref = api.svc.add_run("web")
    (api.data / "departments" / "sales" / "runs" / ref.run_id).mkdir()            # the same id under another team's runs
    (api.data / "departments" / "sales" / "runs" / ref.run_id / "snapshot.json").write_text(json.dumps({"status": "running", "chat": []}))
    for bad in ("elsewhere", "departments/sales/runs/" + ref.run_id, "departments/web/runs/../runs/" + ref.run_id + "/.."):
        ref.dir = bad
        assert ctxmod.run_dir_of(api.svc, "web", ref) is None, bad
        assert api.client.get("/api/state?dept=web").json()["status"] == "idle"
    ref.dir = f"departments/web/runs/{ref.run_id}"
    assert ctxmod.run_dir_of(api.svc, "web", ref) == str(api.data.resolve() / ref.dir)


def test_page_json_marker_hides_runs_up_to_and_including_it(api):
    first, second = (api.svc.add_run("web", run_id=f"j2-20261104-10000{i}-aaaa") for i in (1, 2))
    publish(api.svc, first)
    publish(api.svc, second)
    ctxmod.write_page(api.data, "web", since_run=second.run_id)
    assert api.client.get("/api/state?dept=web").json()["status"] == "idle"
    ctxmod.write_page(api.data, "web", since_run=first.run_id)
    assert api.client.get("/api/state?dept=web").json()["run_id"] == second.run_id


def test_page_json_reads_tolerantly_and_writes_atomically_with_mode_0600(api):
    page = api.data / "departments" / "web" / "page.json"
    for text in ("", "[1]", "{torn", '{"since_run": 5, "next_settings": "x"}'):
        page.write_text(text)
        assert ctxmod.read_page(api.data, "web") == ctxmod.PageState()
    ctxmod.write_page(api.data, "web", next_settings={"J2_OUTPUT": "prd"})
    ctxmod.write_page(api.data, "web", since_run="j2-x")             # a change keeps the other field
    assert json.loads(page.read_text()) == {"since_run": "j2-x", "next_settings": {"J2_OUTPUT": "prd"}}
    assert oct(page.stat().st_mode & 0o777) == "0o600" and [p.name for p in page.parent.iterdir() if p.name.startswith(".page")] == []
    with pytest.raises(ValueError):
        ctxmod.write_page(api.data, "web", other=1)


def test_mount_registers_once(api):
    assert getattr(api.app.state, MOUNT_MARK) is True
    with pytest.raises(RuntimeError, match="already mounted"):
        mount(api.app, api.svc)


def test_every_write_route_depends_on_the_token_guard(api):
    router = build_router(api.svc)
    writes = [r for r in router.routes if r.methods - {"GET", "HEAD", "OPTIONS"}]
    assert {(next(iter(r.methods)), r.path) for r in writes} == {("POST", p) for p in POSTS} | {("PUT", "/api/engine/settings")}
    for route in writes:
        assert api.svc.require_token in [d.dependency for d in route.dependencies], route.path


def test_the_first_value_of_a_repeated_run_parameter_is_the_one_used(api):
    first, second = (api.svc.add_run("web", files={"chat.jsonl": json.dumps({"meta": True}) + "\n"}) for _ in range(2))
    got = api.client.get(f"/api/state?dept=web&run={first.run_id}&run={second.run_id}").json()
    assert got["saved"] == first.run_id


def test_a_resolver_that_answers_with_another_teams_run_is_not_believed(api):
    other = api.svc.add_run("sales", files={"chat.jsonl": json.dumps({"meta": True}) + "\n"})
    api.svc.resolve_run = lambda run_id, dept_id: other                           # a buggy orchestrator
    assert api.client.get(f"/api/state?dept=web&run={other.run_id}").json() == {"error": "not_found"}
    assert api.client.get("/api/state?dept=web").json()["status"] == "idle"
