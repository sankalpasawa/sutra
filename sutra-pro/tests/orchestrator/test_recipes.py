"""Recipes (DV-3, SUTRA_RECIPES_V1): off, nothing exists; on, the owner's words are checked by the note gate, every change is a new version that can be gone back to, a starter cannot be changed, an imported
file is only a draft, starting one makes a plain request that goes the way any request goes, and a project can be turned into a draft by code."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from orchestrator.projects_rig import PRig  # noqa: F401
from orchestrator.test_projects_adopt import BASE, HEADERS, make_app, rows
from orchestrator.test_scripted_conversation import ORG

from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.recipes import REQUEST_MAX, RecipeService, clean_body, parse_markdown, to_markdown
from sutra_app.orchestrator.recipes_starter import STARTERS

BODY = {"overview": "Write the menu.", "procedure": ["Ask what is on sale", "Write each dish in $1 words"], "specifications": ["One page"], "advice": ["Short is good"],
        "forbidden": ["Never invent a price"], "needs": [{"label": "How long each dish may be"}]}


@pytest.fixture
def rig(db, settings, clock, events):
    return PRig(db, settings, clock, events, max_runs=6, max_live=12)


def svc(rig, projects=False):
    return RecipeService(rig.t.db, redact=lambda text: text.replace("hunter2hunter2", "[redacted]"), projects=projects)


# ---- the switch off ---------------------------------------------------------------------------------------------------------------------
def test_with_the_switch_off_no_recipe_route_or_page_exists_before_or_after_the_token(tmp_path):
    app, _c = make_app(tmp_path)
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not [p for p in paths if p.startswith("/api/recipes") or p == "/recipes" or p.endswith("/save-as-recipe")]
    with TestClient(app, base_url=BASE) as client:
        for method, url in (("get", "/api/recipes"), ("get", "/api/recipes/starter-explain-this-folder"), ("get", "/recipes")):
            assert getattr(client, method)(url).status_code == 404, url
        for headers in ({}, HEADERS):
            assert client.post("/api/recipes", json={"title": "x", "body": BODY}, headers=headers).status_code == 404
            assert client.post("/api/recipes/starter-explain-this-folder/start", json={"blanks": [], "client_id": "abcdefgh01"}, headers=headers).status_code == 404
        assert app.state.services.db.conn().execute("SELECT count(*) FROM recipes").fetchone()[0] == 0


# ---- the words are checked ------------------------------------------------------------------------------------------------------------
def test_a_recipe_body_is_cleaned_and_every_refusal_is_in_plain_words():
    clean = clean_body({**BODY, "overview": "  Write   the\nmenu. "})
    assert clean["overview"] == "Write the menu." and clean["needs"] == [{"label": "How long each dish may be"}]
    secret = "ghp_" + "a" * 36
    cases = [({**BODY, "procedure": []}, "at least one step"), ({**BODY, "procedure": ["x"] * 31}, "at most 30"), ({**BODY, "procedure": ["x" * 301]}, "characters long"),
             ({**BODY, "advice": [secret]}, "key, a token or a password"), ({**BODY, "overview": secret}, "key, a token or a password"), ({**BODY, "procedure": ["Use $2"]}, "$2 stands for"),
             ({**BODY, "needs": [{"label": "a"}] * 10}, "at most 9"), ({**BODY, "extra": 1}, "and nothing else"), ({**BODY, "needs": [{"label": ""}]}, "empty"),
             ({**BODY, "needs": [{"label": "x", "more": 1}]}, "asks you for"), ({**BODY, "forbidden": [5]}, "is text"), ("nope", "made of its parts")]
    for body, words in cases:
        with pytest.raises(AppError) as refused:
            clean_body(body)
        assert refused.value.code == "validation" and words in refused.value.message, (words, refused.value.message)
        assert secret not in refused.value.message and "hunter2" not in refused.value.message


# ---- versions ---------------------------------------------------------------------------------------------------------------------------
def test_every_change_is_a_new_version_a_revert_is_one_too_and_the_old_words_can_never_be_changed(rig):
    work = svc(rig)
    made = work.create("Menu", BODY)
    rid = made["id"]
    assert made["version"] == 1 and work.get(rid)["version"] == 1
    second = work.update(rid, "Menu for the cafe", {**BODY, "overview": "Changed."}, "shorter")
    assert second["version"] == 2 and work.get(rid)["title"] == "Menu for the cafe" and work.get(rid)["body"]["overview"] == "Changed."
    assert work.get(rid, 1)["body"]["overview"] == "Write the menu." and work.get(rid)["current_version"] == 2
    back = work.revert(rid, 1)
    assert back["version"] == 3 and work.get(rid)["body"]["overview"] == "Write the menu."
    versions = work.get(rid)["versions"]
    assert [v["version"] for v in versions] == [3, 2, 1] and versions[0]["note"] == "back to version 1" and versions[1]["note"] == "shorter" and all(len(v["sha256"]) == 64 for v in versions)
    conn = rig.t.db.conn()
    for sql in ("UPDATE recipe_versions SET body_json = '{}' WHERE version = 1", "DELETE FROM recipe_versions WHERE version = 1"):
        with pytest.raises(sqlite3.DatabaseError):
            with rig.t.db.tx() as tx:
                tx.conn.execute(sql)
    assert work.get(rid, 1)["body"]["overview"] == "Write the menu." and conn.execute("SELECT count(*) FROM recipe_versions").fetchone()[0] == 3
    with pytest.raises(NotFound):
        work.revert(rid, 9)
    with pytest.raises(NotFound):
        work.get("rcp_000000000000")
    with pytest.raises(AppError):
        work.update(rid, None, {**BODY, "procedure": []})                                                                 # a bad change makes no version
    assert work.get(rid)["current_version"] == 3


def test_a_recipe_can_be_put_away_and_brought_back_and_a_put_away_one_does_not_start(rig):
    work = svc(rig)
    rid = work.create("Menu", BODY)["id"]
    assert [r["id"] for r in work.list()][0] == rid and rid not in [r["id"] for r in work.list(archived=True)]
    work.archive(rid, True)
    assert rid not in [r["id"] for r in work.list()] and [r["id"] for r in work.list(archived=True)] == [rid]
    with pytest.raises(AppError) as put_away:
        work.request_text(rid, ["5"])
    assert put_away.value.code == "busy"
    work.archive(rid, False)
    assert work.request_text(rid, ["5"])[0] == "Menu"


# ---- starters ---------------------------------------------------------------------------------------------------------------------------
def test_the_four_starters_are_read_only_recipes_that_only_read_and_a_copy_is_an_ordinary_recipe(rig):
    work = svc(rig)
    listed = work.list()
    assert [r["kind"] for r in listed] == ["starter"] * 4 and {r["title"] for r in listed} == {"Review my last commits", "Weekly folder health", "Write release notes", "Explain this folder"}
    for rid, starter in STARTERS.items():
        clean_body(starter["body"])                                                                                        # every starter passes the same checks as the owner's words
        if rid != "starter-write-release-notes":
            assert any("Do not change" in line for line in starter["body"]["forbidden"]), rid                                # the read-only ones say so
    with pytest.raises(AppError) as fixed:
        work.update("starter-explain-this-folder", None, BODY)
    assert "Make a copy" in fixed.value.message
    with pytest.raises(AppError):
        work.archive("starter-explain-this-folder", True)
    mine = work.copy_of("starter-review-my-last-commits")
    copy = work.get(mine["id"])
    assert copy["kind"] == "own" and copy["title"] == "Review my last commits (mine)" and copy["body"] == STARTERS["starter-review-my-last-commits"]["body"]
    work.update(mine["id"], None, {**copy["body"], "overview": "Mine."})
    assert STARTERS["starter-review-my-last-commits"]["body"]["overview"] != "Mine."                                       # the starter itself never moved
    with pytest.raises(NotFound):
        work.get("starter-nothing")


# ---- becoming a request ------------------------------------------------------------------------------------------------------------------
def test_a_recipe_becomes_a_plain_request_with_its_blanks_filled_and_its_forbidden_lines_as_never(rig):
    work = svc(rig)
    rid = work.create("Menu", BODY)["id"]
    title, text = work.request_text(rid, ["twenty"])
    assert title == "Menu" and text.startswith("Use my recipe “Menu”. Write the menu.\nDo these steps in order:\n1. Ask what is on sale\n2. Write each dish in twenty words")
    assert "The result must be like this:\n- One page" in text and "Good to know:\n- Short is good" in text and text.endswith("Never do these:\n- Never invent a price")
    assert "$1" not in text
    for blanks in ([], ["a", "b"], "x", [5]):
        with pytest.raises(AppError):
            work.request_text(rid, blanks)
    with pytest.raises(AppError) as secret:
        work.request_text(rid, ["ghp_" + "a" * 36])
    assert "key, a token or a password" in secret.value.message
    big = work.create("Big", {"procedure": ["x" * 290] * 30, "specifications": ["y" * 290] * 20, "advice": ["z" * 290] * 20, "forbidden": []})["id"]
    with pytest.raises(AppError) as long:
        work.request_text(big, [])
    assert "too long" in long.value.message and REQUEST_MAX < 8000


# ---- Markdown ---------------------------------------------------------------------------------------------------------------------------
def test_a_recipe_goes_out_as_markdown_and_comes_back_as_a_draft_that_still_has_to_be_saved(rig):
    work = svc(rig)
    title, text = work.export(work.create("Menu", BODY)["id"])
    assert text.startswith("# Menu\n\n## Overview\nWrite the menu.\n\n## Procedure\n1. Ask what is on sale\n2. Write each dish in $1 words") and "## Needs from you\n1. How long each dish may be" in text
    draft = parse_markdown(text)
    assert draft["title"] == "Menu" and clean_body(draft["body"]) == clean_body(BODY)
    assert rig.t.db.conn().execute("SELECT count(*) FROM recipes").fetchone()[0] == 1                                       # reading a file saved nothing
    for bad in ("no title\n## Procedure\n1. x", "# T\n## Overview\nx", "x" * 31_000, 5):
        with pytest.raises(AppError):
            parse_markdown(bad)
    assert parse_markdown("# T\n## Procedure\n- one\n* two\n3) three\n## Whatever\nignored")["body"]["procedure"] == ["one", "two", "three"]
    assert to_markdown("T", {"procedure": ["a"]}).count("## ") == 6


# ---- from a project ---------------------------------------------------------------------------------------------------------------------
def test_a_finished_project_becomes_a_draft_by_code_and_only_with_the_nodes_on(rig):
    reservation, tasks = rig.request([("a1", "web", []), ("a2", "sales", ["a1"])], title="Cafe site")
    rig.sql("UPDATE tasks SET title = 'Write the menu' WHERE id = ?", tasks["a1"])
    rig.sql("UPDATE tasks SET title = 'Price the dishes' WHERE id = ?", tasks["a2"])
    draft = svc(rig, projects=True).draft_from_project(reservation.project_id)
    assert draft["draft"] is True and draft["title"] == "Cafe site" and draft["body"]["procedure"] == ["Write the menu", "Price the dishes"] and "Saved from the project" in draft["body"]["overview"]
    clean_body(draft["body"])                                                                                               # it already passes the checks the owner's words pass
    assert rig.t.db.conn().execute("SELECT count(*) FROM recipes").fetchone()[0] == 0                                        # a draft is not saved
    with pytest.raises(NotFound):
        svc(rig, projects=False).draft_from_project(reservation.project_id)
    with pytest.raises(NotFound):
        svc(rig, projects=True).draft_from_project("prj_000000000999")


# ---- the routes ---------------------------------------------------------------------------------------------------------------------------
def test_the_routes_need_the_token_refuse_a_bad_body_save_versions_export_import_and_start(tmp_path):
    from orchestrator.test_chat_agent import add_dept, assignments, change_reply, decide, draft
    app, connector = make_app(tmp_path, recipes_v1=True)
    with TestClient(app, base_url=BASE) as client:
        services = app.state.services
        assert [r["kind"] for r in client.get("/api/recipes").json()] == ["starter"] * 4
        assert client.post("/api/recipes", json={"title": "Menu", "body": BODY}).status_code == 401
        assert client.post("/api/recipes", json={"title": "Menu", "body": BODY, "extra": 1}, headers=HEADERS).status_code == 422
        assert client.post("/api/recipes", json={"title": "Menu", "body": {**BODY, "advice": ["ghp_" + "a" * 36]}}, headers=HEADERS).status_code == 422
        made = client.post("/api/recipes", json={"title": "Menu", "body": BODY}, headers=HEADERS)
        assert made.status_code == 201
        rid = made.json()["id"]
        assert client.put(f"/api/recipes/{rid}", json={"body": {**BODY, "overview": "Two."}, "note": "second"}, headers=HEADERS).json() == {"id": rid, "version": 2}
        assert client.get(f"/api/recipes/{rid}?version=1").json()["body"]["overview"] == "Write the menu." and client.get(f"/api/recipes/{rid}").json()["version"] == 2
        assert client.post(f"/api/recipes/{rid}/revert", json={"version": 1}, headers=HEADERS).json()["version"] == 3
        assert client.post(f"/api/recipes/{rid}/revert", json={"version": 0}, headers=HEADERS).status_code == 422
        assert client.get("/api/recipes/rcp_000000000000").status_code == 404
        exported = client.get(f"/api/recipes/{rid}/export")
        assert exported.headers["content-type"].startswith("text/markdown") and "attachment" in exported.headers["content-disposition"] and exported.text.startswith("# Menu")
        imported = client.post("/api/recipes/import", json={"markdown": exported.text}, headers=HEADERS).json()
        assert imported["draft"] is True and imported["title"] == "Menu" and len(client.get("/api/recipes").json()) == 5          # nothing was saved by the import
        assert client.post("/api/recipes/import", json={"markdown": "# T\n## Procedure\n- ghp_" + "a" * 36}, headers=HEADERS).status_code == 422
        assert client.post("/api/recipes/import", json={"markdown": "nothing"}, headers=HEADERS).status_code == 422
        assert client.post("/api/recipes/starter-explain-this-folder/copy", json={}, headers=HEADERS).status_code == 201
        assert client.put("/api/recipes/starter-explain-this-folder", json={"body": BODY}, headers=HEADERS).status_code == 422
        # starting: the recipe becomes the owner's line in the org chat, once
        sent = client.post(f"/api/recipes/{rid}/start", json={"blanks": ["twenty"], "client_id": "recipe-0001"}, headers=HEADERS)
        assert sent.status_code == 202 and sent.json()["duplicate"] is False and sent.json()["recipe"] == "Menu"
        again = client.post(f"/api/recipes/{rid}/start", json={"blanks": ["twenty"], "client_id": "recipe-0001"}, headers=HEADERS)
        assert again.status_code == 200 and again.json()["duplicate"] is True
        lines = rows(services, "SELECT text FROM chat_messages WHERE role = 'user' AND session_id = ?", ORG)
        assert len(lines) == 1 and lines[0]["text"].startswith("Use my recipe “Menu”.") and "twenty words" in lines[0]["text"]
        assert client.post(f"/api/recipes/{rid}/start", json={"blanks": [], "client_id": "recipe-0002"}, headers=HEADERS).status_code == 422          # the wrong number of blanks
        assert client.post(f"/api/recipes/{rid}/start", json={"blanks": ["x"], "client_id": "short"}, headers=HEADERS).status_code == 422
        assert client.post(f"/api/recipes/{rid}/archive", json={"archived": True}, headers=HEADERS).json()["status"] == "archived"
        assert client.post(f"/api/recipes/{rid}/start", json={"blanks": ["x"], "client_id": "recipe-0003"}, headers=HEADERS).status_code == 409
        assert client.post("/api/projects/prj_000000000001/save-as-recipe", json={}, headers=HEADERS).status_code == 404                 # needs the nodes too


def test_saving_a_project_as_a_recipe_through_the_route_gives_a_draft(tmp_path):
    from orchestrator.test_project_page_route import one_project
    app, connector = make_app(tmp_path, recipes_v1=True, nodes_v1=True)
    client = one_project(app, connector)
    try:
        project = rows(app.state.services, "SELECT id FROM projects")[0]["id"]
        found = client.post(f"/api/projects/{project}/save-as-recipe", json={}, headers=HEADERS)
        assert found.status_code == 200 and found.json()["draft"] is True and len(found.json()["body"]["procedure"]) == 2
        assert client.post(f"/api/projects/{project}/save-as-recipe", json={}).status_code == 401
        assert len(client.get("/api/recipes").json()) == 4                                                                               # only the starters: nothing was saved
    finally:
        client.__exit__(None, None, None)


def test_the_recipes_page_exists_only_with_the_switch_on_and_every_file_it_names_is_served(tmp_path):
    import re
    off, _c = make_app(tmp_path / "off")
    with TestClient(off, base_url=BASE) as client:
        assert client.get("/recipes").status_code == 404
        assert "/recipes" not in client.get("/").text
    on, _c = make_app(tmp_path / "on", recipes_v1=True)
    with TestClient(on, base_url=BASE) as client:
        page = client.get("/recipes")
        assert page.status_code == 200 and 'id="recipes-root"' in page.text and '"page":"recipes"' in page.text and "<!--SUTRA-BOOT-->" not in page.text
        assert client.head("/recipes").status_code == 200 and client.get("/work").status_code == 404                      # one switch for each page
        for name in re.findall(r'(?:src|href)="(/ui/[^"]+)"', page.text):
            assert client.get(name).status_code == 200, name
