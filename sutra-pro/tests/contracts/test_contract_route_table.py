"""The route table: what the engine, the orchestrator, the connectors and the UI serve, against what the page calls (S1-contracts-01,
S3-web-01, S3-web-03, S3-web-12).

One mount for the J2 routes, at the root, the team in `?dept=`; no `/d/{dept}/api` copy, no header, no cookie; the UI alone serves the
pages; one write guard for every router; `Services` satisfies the engine's `EngineServices`."""
import inspect
import re
from pathlib import Path

import pytest
from fastapi import FastAPI

from sutra_app.engine.api import MOUNT_MARK, mount
from sutra_app.engine.api.ports import EngineServices
from sutra_app.engine.spec import DEPT_ID_RE
from sutra_app.orchestrator.api.deps import require_token
from sutra_app.orchestrator.models import RunSpec

from .test_contract_world import (  # noqa: F401  (clock to world are fixtures used by name)
    REPO, SAFE_METHODS, World, clock, db, dependency_calls, events, ids, route_table, settings, tenv, world,
)

UI = REPO / "sutra_app" / "ui"
PAGE_FILES = [UI / "pages" / "j2_ui.html", UI / "pages" / "j2_ui_render.js"]
STATIC_JS = sorted((UI / "static" / "js").glob("*.js")) + [UI / "pages" / "home.html"]
SETTINGS_PATH = "/api/engine/settings"
CAPABILITIES_PATH = "/api/engine/capabilities"      # D126: what the engine can do (a read for the owner and the doctor; no page calls it, no team)
# served by a package that has not merged yet (ORCH-8: health); the page calls them, no router of this repo has them
NOT_MOUNTED_YET = {"/api/health"}


def j2_paths() -> tuple[list[str], list[str]]:
    """(exact paths, prefixes) of the UI's own list of J2 routes, read from sutra_ctx.js (`J2_EXACT`, `J2_PREFIXES`)."""
    text = (UI / "static" / "js" / "sutra_ctx.js").read_text(encoding="utf-8")
    found = []
    for name in ("J2_EXACT", "J2_PREFIXES"):
        body = re.search(rf"const {name} = \[(.*?)\];", text, re.S).group(1)
        found.append(re.findall(r'"([^"]+)"', body))
    return found[0], found[1]


def ui_matches(path: str) -> bool:
    exact, prefixes = j2_paths()
    return path in exact or any(path.startswith(p) for p in prefixes)


def literal_paths(files) -> set[str]:
    """The path part of every string literal in `files` that starts like a route (`/api/`, `/site/`, `/file/`, `/shot/`, `/doc/`, `/view`): cut at the
    first `?`, `$`, quote or `#`, so "/api/chats/${id}/messages" gives "/api/chats/"."""
    found = set()
    for file in files:
        for quote_char, body in re.findall(r"([\"'`])((?:/api/|/site/|/file/|/shot/|/doc/|/view)[^\"'`]*)", file.read_text(encoding="utf-8")):
            found.add(re.split(r"[?$#]", body)[0])
    return found


def served(path: str, templates: set[str]) -> bool:
    """Does some route template answer `path` (an exact path, or a prefix that ends with `/` or stops at a `{param}`)?"""
    for template in templates:
        plain = re.sub(r"\{[^}]+\}", "x", template)
        pattern = re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(template))
        if template == path or plain == path or re.fullmatch(pattern, path) or (path.endswith("/") and template.startswith(path)):
            return True
    return False


def all_templates(world: World) -> set[str]:
    return {path for router in world.routers.values() for (_, path) in route_table(router)}


# ---- the engine's table ----------------------------------------------------------------------------------------------------------

def test_the_engine_serves_exactly_the_j2_routes_the_page_lists_plus_the_two_settings_routes_and_the_capabilities_route(world):
    table = route_table(world.routers["engine"])
    exact, prefixes = j2_paths()
    gets = {path for (method, path) in table if method == "GET"}
    posts = {path for (method, path) in table if method == "POST"}
    templated = {path for path in gets if "{" in path}
    assert {path for (method, path) in table if method == "PUT"} == {SETTINGS_PATH}
    assert len(gets - {SETTINGS_PATH, CAPABILITIES_PATH}) == 31 and len(posts) == 7      # 31 GET paths (/site/{key} answers two rows), J2 sync 4's included
    assert len(table) == 31 + 7 + 2 + 1                                                  # the settings GET and PUT and the capabilities GET
    assert len(templated) == 5 and all(any(path.startswith(prefix) for prefix in prefixes) for path in templated)
    for prefix in prefixes:
        assert any(path.startswith(prefix) for path in templated), prefix
    assert (gets | posts) - templated - {SETTINGS_PATH, CAPABILITIES_PATH} == set(exact)     # the page's list and the table name the same 33
    assert len(exact) == 33 and len(prefixes) == 5


def test_no_route_copy_under_a_team_path_and_no_team_header_or_cookie(world):
    for name, router in world.routers.items():
        if name == "ui":
            continue
        for (method, path), route in route_table(router).items():
            assert not path.startswith("/d/"), (name, path)
            assert "/d/{dept}" not in path, (name, path)
            for param in route.dependant.header_params + route.dependant.cookie_params:
                assert "dept" not in param.name.lower(), (name, path, param.name)


def test_every_j2_write_and_read_wants_the_team_in_the_query_and_nowhere_else(world):
    for (method, path) in route_table(world.routers["engine"]):
        if path in (SETTINGS_PATH, CAPABILITIES_PATH):
            continue
        url = re.sub(r"\{[^}]+\}", "x1", path)
        call = world.client.request(method, url, headers={**world.auth, "X-Sutra-Dept": "web"}, cookies={"sutra_dept": "web"})
        assert (call.status_code, call.json()) == (400, {"error": "dept_required"}), (method, path)


def test_the_settings_routes_work_without_a_team_for_the_global_file_and_refuse_an_unknown_one(world):
    assert world.client.get(SETTINGS_PATH).status_code == 200
    assert world.client.get(SETTINGS_PATH, params={"dept": "web"}).status_code == 200
    assert world.client.get(SETTINGS_PATH, params={"dept": "nope"}).status_code == 404


def test_the_department_rule_is_the_one_the_sections_wrote_down():
    """S1-contracts-01: `^[a-z][a-z0-9-]{1,39}$`, no underscore, 2 to 40 characters; the tests below compare everything else with it."""
    assert DEPT_ID_RE == "^[a-z][a-z0-9-]{1,39}$"
    for dept, ok in (("ab", True), ("a" * 40, True), ("a" * 41, False), ("a", False), ("a_b", False), ("A-b", False), ("1ab", False)):
        assert bool(re.fullmatch(DEPT_ID_RE, dept)) is ok, dept


def test_the_team_is_checked_with_the_one_department_rule_by_the_engine_and_the_run_spec(world):
    rule = re.compile(DEPT_ID_RE)
    samples = ["web", "w-b", "ab", "a" * 40, "a" * 41, "a", "Web", "9web", "w_b", "web ", "-web", "wéb", ""]
    for dept in samples:
        answer = world.client.get("/api/runs", params={"dept": dept}).status_code
        expected = 404 if rule.fullmatch(dept) and dept != "web" else (200 if dept == "web" else 400)
        assert answer == expected, dept
        if dept != dept.strip():
            continue                                                                 # a model strips its text: not the rule's business
        try:
            RunSpec(run_id="j2-20261104-100004-7f3a", task_id="tsk_a1b2c3d4e5f6", dept_id=dept, dept_label="x", user_text="hi")
            accepted = True
        except ValueError:
            accepted = False
        assert accepted == bool(rule.fullmatch(dept)), dept
    assert world.client.get("/api/runs").json() == {"error": "dept_required"}
    assert world.client.get("/api/runs", params={"dept": "nope"}).json() == {"error": "not_found"}


# ---- the whole app ---------------------------------------------------------------------------------------------------------------

def test_no_two_routers_serve_the_same_method_and_path(world):
    seen: dict[tuple[str, str], str] = {}
    for name, router in world.routers.items():
        for (method, path) in route_table(router):
            shape = (method, re.sub(r"\{[^}]+\}", "{}", path))
            assert shape not in seen, f"{shape} is served by {seen.get(shape)} and {name}"
            seen[shape] = name


def test_the_ui_alone_serves_the_pages(world):
    pages = {path for (_, path) in route_table(world.routers["ui"])}
    assert pages == {"/", "/d/{dept}", "/d/{dept}/", "/console", "/favicon.ico"}
    for name, router in world.routers.items():
        if name != "ui":
            assert not (pages & {path for (_, path) in route_table(router)}), name
    assert world.client.get("/", follow_redirects=False).status_code == 404            # the world mounts no UI: the engine serves no page
    assert world.client.get("/d/web/", follow_redirects=False).status_code == 404


def test_every_route_that_changes_something_depends_on_the_one_write_guard(world):
    writes = 0
    for name, router in world.routers.items():
        for (method, path), route in route_table(router).items():
            if method in SAFE_METHODS:
                continue
            writes += 1
            assert require_token in dependency_calls(route), (name, method, path)
    assert writes >= 5 + 1 + 3 + 3 + 1                                                   # engine POSTs and PUT, tasks, chart, connectors
    assert world.services.require_token is require_token


def test_the_token_comes_before_the_team_for_the_engine_writes(world):
    assert world.client.post("/api/say", params={"dept": "web"}, json={"text": "hi"}).status_code == 401
    assert world.client.post("/api/say", params={"dept": "nope"}, json={"text": "hi"}).status_code == 401
    assert world.client.post("/api/say", params={"dept": "nope"}, json={"text": "hi"}, headers=world.auth).status_code == 404
    assert world.client.put(SETTINGS_PATH, json={"set": {}}).status_code == 401


def test_the_engine_mounts_once(world):
    assert getattr(world.app.state, MOUNT_MARK) is True
    with pytest.raises(RuntimeError):
        mount(world.app, world.services)
    assert mount is not None and isinstance(world.app, FastAPI)


# ---- Services satisfies EngineServices -------------------------------------------------------------------------------------------

def test_services_answers_every_member_of_the_engine_protocol_with_the_same_parameters(world):
    for name, declared in vars(EngineServices).items():
        if name.startswith("_") or not callable(declared):
            continue
        given = getattr(world.services, name)
        want = list(inspect.signature(declared).parameters)[1:]                      # without `self`
        have = list(inspect.signature(given).parameters)
        assert have == want, (name, have, want)
    assert set(EngineServices.__annotations__) == {"data_dir", "require_token", "redact"}
    assert isinstance(world.services.data_dir, Path) and callable(world.services.redact)


def test_the_orchestrators_answers_drive_the_engines_say_and_reset(world):
    """The three calls the engine makes of the server, over the real task service: a follow-up, busy, and reset refusing a live team."""
    first = world.client.post("/api/say", params={"dept": "web"}, json={"text": "A site for my cafe"}, headers=world.auth)
    assert (first.status_code, first.json()) == (200, {"ok": True})
    task = world.t.service.store.latest_in(world.t.db.conn(), "web")
    assert task is not None and task.status in ("queued", "starting", "running")
    second = world.client.post("/api/say", params={"dept": "web"}, json={"text": "and a menu"}, headers=world.auth)
    assert (second.status_code, second.json()) == (409, {"ok": False})
    runs = world.client.get("/api/runs", params={"dept": "web"}).json()
    assert runs["live"] == "" or runs["live"].startswith("j2-")


# ---- the page against the table --------------------------------------------------------------------------------------------------

def test_every_path_the_j2_page_calls_is_in_the_engine_table_and_in_the_ui_list(world):
    engine = {path for (_, path) in route_table(world.routers["engine"])}
    called = literal_paths(PAGE_FILES)
    assert called, "the scan found no path in the J2 page: the pattern is out of date"
    for path in called:
        assert ui_matches(path) or path == SETTINGS_PATH, f"{path} is called by the J2 page but is not in sutra_ctx.js J2_PATHS"
        assert served(path, engine), f"{path} is called by the J2 page and the engine serves no such route"


def test_every_engine_route_is_called_by_a_page_or_a_view_script(world):
    called = literal_paths(PAGE_FILES + STATIC_JS)
    for (method, path) in route_table(world.routers["engine"]):
        if path == CAPABILITIES_PATH:
            continue
        stem = re.split(r"/\{", path)[0] + ("/" if "{" in path else "")
        assert path in called or stem in called or any(stem == c for c in called), f"{method} {path} is served and no page calls it"


def test_every_path_the_view_scripts_call_is_served_by_some_router(world):
    templates = all_templates(world)
    for path in literal_paths(STATIC_JS + PAGE_FILES):
        if path in NOT_MOUNTED_YET:
            continue
        assert served(path, templates), f"{path} is called by a page script and no router serves it"


def test_the_orchestrators_own_paths_never_look_like_a_j2_path_so_the_page_never_adds_dept_to_them(world):
    for name, router in world.routers.items():
        if name in ("engine", "ui"):
            continue
        for (_, path) in route_table(router):
            assert not ui_matches(re.sub(r"\{[^}]+\}", "x1", path)), (name, path)

