"""Standing rules of a team (GAP2 rules-notes): the store, the refusals, and what reaches a run's framing.

The real `TaskService` runs on `TEnv` (test_tasks) with a fake launcher; what a run is told is read back from its `task.json`, the document the engine
reads, whose `framing` the engine host posts as the one system line "Context from the team lead: ...". The routes run over a `Services` with no wiring
at all: the store is built from `services.db` on each call."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator.test_tasks import TEnv, tenv  # noqa: F401  (tenv is a fixture)

from sutra_app.library.practice import BLOCK_HEADING, MAX_RULES
from sutra_app.orchestrator.api import rules_notes
from sutra_app.orchestrator.api.deps import install_error_handlers, redacted_response_class
from sutra_app.orchestrator.errors import AppError, NotFound
from sutra_app.orchestrator.models import RunSpec
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.services import Services
from sutra_app.orchestrator.standing_rules import FRAMING_MAX, KEY, RuleIn, StandingRules, framing_for

TOKEN = "X-Sutra-Token"
SECRET = "sk-aaaaaaaa11111111"


def rules_of(t: TEnv) -> StandingRules:
    return StandingRules(t.db, Redactor(None, environ={}))


def spec_of(t: TEnv, task_id: str) -> RunSpec:
    return RunSpec.model_validate_json((t.run_dir(task_id) / "task.json").read_text())


def started_framing(t: TEnv, dept="web", framing="") -> str:
    """Create a task, start it and read the framing the run was given."""
    task = t.new(dept, "Build a page", framing=framing)
    t.run(t.service.start_ready())
    return spec_of(t, task.id).framing


# ---- the store -------------------------------------------------------------------------------------------------------------------

def test_the_owners_rules_are_stored_per_team_and_read_back(tenv):
    rules = rules_of(tenv)
    assert rules.get("web").rules == [] and rules.get("web").pack is None and rules.get("web").declined == []
    out = rules.put("web", [RuleIn(tag="never", text="Never email a client without asking."), RuleIn(tag="always", text="  Use   plain words. ")])
    assert [(r.tag, r.text) for r in out.rules] == [("never", "Never email a client without asking."), ("always", "Use plain words.")]
    assert rules.get("web") == out and rules.get("sales").rules == []                   # another team is untouched
    assert tenv.one("SELECT count(*) FROM meta WHERE key = ?", KEY.format("web")) == 1 and tenv.one("SELECT count(*) FROM meta WHERE key LIKE 'rules:%'") == 1


def test_a_put_that_leaves_a_key_out_leaves_that_part_alone(tenv):
    rules = rules_of(tenv)
    rules.put("web", [RuleIn(tag="ask", text="Ask before a purchase.")], pack="money-movement")
    assert rules.put("web", None).pack.id == "money-movement" and len(rules.get("web").rules) == 1          # nothing named: nothing changed
    assert rules.put("web", [RuleIn(tag="ask", text="Ask before a purchase.")], pack=None).pack is None    # pack null takes the pick off
    assert rules.put("web", [], pack=False).rules == []                                                    # an empty list clears the rules
    assert rules.put("web", None, pack="product-build").pack.name == "Product build"


def test_an_unknown_team_is_not_found_and_an_unknown_pick_is_a_422(tenv):
    rules = rules_of(tenv)
    for call in (lambda: rules.get("nope"), lambda: rules.put("nope", []), lambda: rules.accept("nope", "money-movement"), lambda: rules.decline("nope", "x")):
        with pytest.raises(NotFound):
            call()
    with pytest.raises(AppError) as caught:
        rules.put("web", None, pack="made-up")
    assert caught.value.code == "validation" and "money-movement" in caught.value.details["violations"][0]["message"]


def test_a_rule_with_a_key_in_it_is_refused_by_name_and_nothing_is_stored(tenv):
    rules = rules_of(tenv)
    with pytest.raises(AppError) as caught:
        rules.put("web", [RuleIn(tag="always", text="Fine rule."), RuleIn(tag="never", text=f"Never share {SECRET} with anyone.")])
    found = caught.value.details["violations"]
    assert caught.value.code == "validation" and [v["path"] for v in found] == ["rules.1.text"] and "key, a token or a password" in found[0]["message"]
    assert SECRET not in str(caught.value.details)
    assert rules.get("web").rules == []                                                                  # all or nothing


def test_the_app_s_own_secret_values_are_refused_too(tenv):
    rules = StandingRules(tenv.db, Redactor(None, environ={"MY_API_TOKEN": "hunter2hunter2"}))
    with pytest.raises(AppError):
        rules.put("web", [RuleIn(tag="always", text="Log in with hunter2hunter2 first.")])


def test_empty_long_repeated_and_too_many_rules_are_refused_with_a_plain_sentence(tenv):
    rules = rules_of(tenv)
    with pytest.raises(AppError) as caught:
        rules.put("web", [RuleIn(tag="always", text="   ")])
    assert caught.value.details["violations"][0]["message"] == "That line is empty."
    with pytest.raises(AppError) as caught:
        rules.put("web", [RuleIn(tag="always", text="x" * 301)])
    assert "301 characters long; the most is 300" in caught.value.details["violations"][0]["message"]
    with pytest.raises(AppError) as caught:
        rules.put("web", [RuleIn(tag="never", text="Never publish prices."), RuleIn(tag="never", text="publish  PRICES")])
    assert caught.value.details["violations"][0]["path"] == "rules.1.text" and "already has this rule (rule 1)" in caught.value.details["violations"][0]["message"]
    with pytest.raises(AppError) as caught:
        rules.put("web", [RuleIn(tag="always", text=f"Rule number {n}.") for n in range(MAX_RULES + 1)])
    assert caught.value.details["violations"][0]["code"] == "too_many" and str(MAX_RULES) in caught.value.details["violations"][0]["message"]
    assert len(rules.put("web", [RuleIn(tag="always", text=f"Rule number {n}.") for n in range(MAX_RULES)]).rules) == MAX_RULES    # the full list is fine


def test_a_rule_cannot_say_a_pick_s_line_more_loosely(tenv):
    rules = rules_of(tenv)
    rules.put("web", None, pack="product-build")
    # the pick says: a promise to a user outside the team ... is put to the owner first (ask); the owner may not make it a plain 'always'
    # with the same words, but may say it as strictly or more strictly
    line = "A promise to a user outside the team (a date, a feature, a price) is put to the owner first."
    assert rules.put("web", [RuleIn(tag="never", text=line)]).rules[0].tag == "never"
    rules.put("web", None, pack="money-movement")
    with pytest.raises(AppError) as caught:
        rules.put("web", [RuleIn(tag="ask", text="A payment and its reconciliation are never held by the same person or model: one makes, another checks.")])
    assert "A rule cannot say it more loosely" in caught.value.details["violations"][0]["message"]


def test_accept_picks_and_decline_is_remembered_and_a_later_accept_forgets_it(tenv):
    rules = rules_of(tenv)
    assert rules.decline("web", "money-movement").declined == ["money-movement"]
    assert rules.decline("web", "money-movement").declined == ["money-movement"]                         # once only
    assert rules.decline("web", "made-up").declined == ["money-movement"]                                # an unknown pick is not recorded
    out = rules.accept("web", "money-movement")
    assert out.pack.id == "money-movement" and out.declined == []


# ---- what a run is told ------------------------------------------------------------------------------------------------------------

def test_a_team_with_no_rules_gets_byte_identical_framing(tenv):
    assert started_framing(tenv, framing="The owner wants it by Friday.") == "The owner wants it by Friday."
    assert framing_for(tenv.db.conn(), "sales", "") == ""


def test_a_run_carries_the_rules_in_front_of_the_brief(tenv):
    rules_of(tenv).put("web", [RuleIn(tag="never", text="Never email a client without asking.")], pack="money-movement")
    framing = started_framing(tenv, framing="Build the cafe page.")
    assert framing.startswith(BLOCK_HEADING) and framing.endswith("\n\nBuild the cafe page.")
    assert "- Never: Never email a client without asking." in framing and "Practice \"Money movement\"" in framing
    assert len(framing) <= FRAMING_MAX


def test_a_run_with_no_brief_still_carries_the_rules(tenv):
    rules_of(tenv).put("web", [RuleIn(tag="always", text="Use plain words.")])
    assert started_framing(tenv) == "Standing rules from the owner (they apply to every task of this team and come before the request; " \
        "where one meets the request, ask the owner):\n- Always: Use plain words."


def test_a_rule_reaches_only_its_own_team(tenv):
    rules_of(tenv).put("web", [RuleIn(tag="never", text="Never email a client without asking.")])
    assert started_framing(tenv, "sales", framing="Write the quote.") == "Write the quote."


def test_a_queued_task_picks_up_an_edit_made_before_it_starts(tenv):
    first = tenv.new("web", "First job")
    second = tenv.new("web", "Second job")                      # waits behind the first: one live task per team
    tenv.run(tenv.service.start_ready())
    assert tenv.status(first.id) == "starting" and tenv.status(second.id) == "queued"
    rules_of(tenv).put("web", [RuleIn(tag="always", text="Use plain words.")])                          # written while the second one waits
    tenv.projector.mark_ended(first.id, "done", "ok")
    tenv.run(tenv.service.start_ready())
    assert spec_of(tenv, first.id).framing == "" and "- Always: Use plain words." in spec_of(tenv, second.id).framing
    assert tenv.row(second.id).framing == ""                    # the stored task keeps the chat agent's own words; the rules are added at the start


def test_a_retry_keeps_one_block_and_its_attempt_note(tenv):
    rules_of(tenv).put("web", [RuleIn(tag="always", text="Use plain words.")])
    first = tenv.started(framing="The owner wants it by Friday.")
    tenv.projector.mark_ended(first, "crashed", "ModelError: quota")
    retried = tenv.run(tenv.service.retry(first))
    framing = spec_of(tenv, retried.id).framing
    assert framing.count(BLOCK_HEADING) == 1 and framing.startswith(BLOCK_HEADING)
    assert "The owner wants it by Friday." in framing and "This is attempt 2 of this request." in framing


def test_a_damaged_rules_row_never_keeps_a_team_from_starting(tenv):
    tenv.sql("INSERT INTO meta(key, value) VALUES ('rules:web', '{not json')")
    assert started_framing(tenv, framing="Build it.") == "Build it."
    tenv.sql("UPDATE meta SET value = ? WHERE key = 'rules:web'", '{"rules": [{"tag": "go", "text": "x"}, 5, {"tag": "never", "text": "Never lie."}], "pack": "gone"}')
    assert "- Never: Never lie." in framing_for(tenv.db.conn(), "web", "x") and "Practice" not in framing_for(tenv.db.conn(), "web", "x")


# ---- the routes --------------------------------------------------------------------------------------------------------------------

@pytest.fixture
def client(tenv):
    app = FastAPI()
    services = Services(settings=tenv.settings, version="test", db=tenv.db, redact=Redactor(None, environ={}), clock=tenv.clock)
    app.state.services = services
    install_error_handlers(app, redacted_response_class(Redactor(None, environ={})))
    app.include_router(rules_notes.build_router())
    return TestClient(app, base_url="http://127.0.0.1:8780", raise_server_exceptions=False)


@pytest.fixture
def auth(tenv):
    return {TOKEN: tenv.settings.token}


def test_the_packs_are_listed_with_the_lines_each_adds(client):
    packs = client.get("/api/packs").json()
    assert [p["id"] for p in packs] == ["money-movement", "product-build"]
    assert {l["function"] for l in packs[0]["lines"]} == {"identity", "adaptation", "priority", "coordination", "audit"}
    assert set(packs[0]) == {"id", "name", "use_case", "fits", "lines"} and set(packs[0]["lines"][0]) == {"function", "tag", "text"}


def test_reading_the_rules_needs_no_token_and_writing_does(client, auth):
    assert client.get("/api/departments/web/rules").json()["rules"] == []
    body = {"rules": [{"tag": "never", "text": "Never email a client without asking."}], "pack": "money-movement"}
    assert client.put("/api/departments/web/rules", json=body).status_code == 401
    assert client.put("/api/departments/web/rules", json=body, headers={TOKEN: "wrong-token-wrong-token"}).status_code == 401
    done = client.put("/api/departments/web/rules", json=body, headers=auth)
    assert done.status_code == 200 and done.json()["pack"]["id"] == "money-movement" and done.json()["rules"][0]["tag"] == "never"
    assert client.get("/api/departments/web/rules").json() == done.json() and done.json()["max_rules"] == MAX_RULES


def test_the_routes_refuse_in_the_error_envelope(client, auth):
    assert client.get("/api/departments/nope/rules").status_code == 404
    assert client.put("/api/departments/nope/rules", json={}, headers=auth).status_code == 404
    refused = client.put("/api/departments/web/rules", json={"rules": [{"tag": "never", "text": f"Never share {SECRET}."}]}, headers=auth)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "validation" and SECRET not in refused.text
    assert refused.json()["error"]["details"]["violations"][0]["path"] == "rules.0.text"
    for bad in ({"rules": [{"tag": "go", "text": "x"}]}, {"rules": [{"tag": "never"}]}, {"extra": 1}, {"pack": 5}):
        assert client.put("/api/departments/web/rules", json=bad, headers=auth).status_code == 422, bad
    assert client.put("/api/departments/web/rules", json={"pack": "made-up"}, headers=auth).status_code == 422


def test_a_put_with_pack_null_takes_the_pick_off_and_an_empty_body_changes_nothing(client, auth):
    client.put("/api/departments/web/rules", json={"pack": "product-build", "rules": [{"tag": "always", "text": "Be brief."}]}, headers=auth)
    assert client.put("/api/departments/web/rules", json={}, headers=auth).json()["pack"]["id"] == "product-build"
    off = client.put("/api/departments/web/rules", json={"pack": None}, headers=auth).json()
    assert off["pack"] is None and off["rules"][0]["text"] == "Be brief."


# ---- two windows (QA org-chat-teams) ---------------------------------------------------------------------------------------------

def test_a_list_saved_from_a_stale_read_is_refused_and_nothing_is_lost(client, auth):
    """Window B still shows the empty list when window A has added a rule: B's save used to replace A's rule without a word. The read carries a
    `rev` of the list, the save hands it back, and a list that changed since is a 422 `validation` (violation `rev`, code `stale_rules`) that stores nothing
    and carries the list as it is now in `details.current`."""
    url = "/api/departments/web/rules"
    empty = client.get(url).json()
    assert isinstance(empty["rev"], str) and empty["rev"]
    a = client.put(url, json={"rules": [{"tag": "always", "text": "Always quote prices in INR"}], "rev": empty["rev"]}, headers=auth)
    assert a.status_code == 200 and a.json()["rev"] != empty["rev"] and client.get(url).json() == a.json()
    b = client.put(url, json={"rules": [{"tag": "always", "text": "Always mention same-day delivery"}], "rev": empty["rev"]}, headers=auth)
    error = b.json()["error"]
    assert b.status_code == 422 and error["code"] == "validation"
    assert [(v["path"], v["code"]) for v in error["details"]["violations"]] == [("rev", "stale_rules")] and "another window" in error["details"]["violations"][0]["message"]
    assert error["details"]["current"] == a.json()                                              # the page can show the list as it is now
    assert [r["text"] for r in client.get(url).json()["rules"]] == ["Always quote prices in INR"]
    again = client.put(url, json={"rules": [*a.json()["rules"], {"tag": "always", "text": "Always mention same-day delivery"}], "rev": a.json()["rev"]}, headers=auth)
    assert again.status_code == 200 and [r["text"] for r in again.json()["rules"]] == ["Always quote prices in INR", "Always mention same-day delivery"]


def test_removing_by_place_from_a_stale_list_is_refused_too(client, auth):
    url = "/api/departments/web/rules"
    first = client.put(url, json={"rules": [{"tag": "always", "text": "Be brief."}, {"tag": "never", "text": "Never guess."}]}, headers=auth).json()
    client.put(url, json={"rules": [{"tag": "never", "text": "Never guess."}], "rev": first["rev"]}, headers=auth)           # window A removes the first line
    stale = client.put(url, json={"rules": [{"tag": "always", "text": "Be brief."}], "rev": first["rev"]}, headers=auth)    # window B removes by place from the old list
    assert stale.status_code == 422 and [r["text"] for r in client.get(url).json()["rules"]] == ["Never guess."]


def test_a_save_without_a_rev_and_a_pick_alone_work_as_before(client, auth):
    url = "/api/departments/web/rules"
    first = client.get(url).json()
    client.put(url, json={"rules": [{"tag": "always", "text": "Be brief."}]}, headers=auth)                  # a script that sends no rev replaces the list
    assert client.put(url, json={"rules": [{"tag": "never", "text": "Never guess."}]}, headers=auth).status_code == 200
    picked = client.put(url, json={"pack": "product-build", "rev": first["rev"]}, headers=auth)              # no list in the body: a stale rev has nothing to protect
    assert picked.status_code == 200 and picked.json()["pack"]["id"] == "product-build" and picked.json()["rules"][0]["text"] == "Never guess."
    assert client.put(url, json={"rules": [], "rev": ""}, headers=auth).status_code == 422                   # a rev is a word, never empty


def test_the_rev_follows_the_list_and_not_the_pick(tenv):
    rules = rules_of(tenv)
    one = rules.put("web", [RuleIn(tag="ask", text="Ask before a purchase.")])
    assert rules.put("web", None, pack="money-movement").rev == one.rev and rules.get("web").rev == one.rev
    two = rules.put("web", [RuleIn(tag="ask", text="Ask before a purchase."), RuleIn(tag="always", text="Be brief.")])
    assert two.rev != one.rev
    assert rules_of(tenv).get("sales").rev == rules_of(tenv).get("sales").rev != one.rev
    with pytest.raises(AppError) as info:
        rules.put("web", [], rev="not-the-current-one")
    assert info.value.code == "validation" and info.value.details["violations"][0]["code"] == "stale_rules" and info.value.details["current"]["rev"] == two.rev
