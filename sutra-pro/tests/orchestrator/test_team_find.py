"""TeamFind (gap package chart-insight): find a team or its work across the org, with the reason it matched.

The old org search re-expressed over Pro's tables: team names, purposes and divisions from the live chart, task titles and outcomes, ranked name over
purpose over task over outcome, one character is not a search, a node that was merged away never comes back, and a read that writes nothing."""
import pytest
from factories_org import add_op, dept_op, merge_op, rename_op
from orchestrator.test_chart_store import Env

from sutra_app.orchestrator.team_find import LIMIT, MIN_CHARS, TeamFind, words_of


@pytest.fixture
def built(db, settings, clock, events):
    """Sales (Leads, Quotes), Web (Menu), as the real apply path makes them."""
    env = Env(db, settings, clock, events).build()
    env.apply(rename_op("sales", purpose="Quotes and leads for the shop"))
    env.apply(rename_op("quotes", purpose="Pricing pages we send to buyers"))
    return env


def task(env, n: int, dept: str, *, title: str, outcome: str = "", scope: str | None = None) -> None:
    env.sql("INSERT INTO tasks(id, dept_id, scope_node_id, title, user_text, status, outcome, created_at) VALUES (?,?,?,?,?,?,?,?)",
            f"tsk_{n:012x}", dept, scope, title, "u", "done", outcome, n)


def find(env, q: str, **kw):
    return TeamFind(env.db).search(q, **kw)


def snapshot(env) -> dict:
    conn = env.db.conn()
    names = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {n: [tuple(r) for r in conn.execute(f'SELECT * FROM "{n}" ORDER BY rowid')] for n in names if not n.startswith("chat_search")}


def rows(env, q: str) -> list[tuple]:
    return [(r.node_id, r.matched_on) for r in find(env, q).teams]


# ---- what is looked at ------------------------------------------------------------------------------------------------------------

def test_a_purpose_only_hit_says_it_matched_on_the_purpose_and_shows_the_words_around_it(built):
    out = find(built, "pricing")
    [hit] = out.teams
    assert (hit.node_id, hit.team_id, hit.kind, hit.matched_on) == ("quotes", "sales", "division", ["purpose"])
    assert hit.address == "Sales > Quotes" and hit.team_name == "Sales" and hit.snippet == "Pricing pages we send to buyers"


def test_a_name_hit_shows_what_the_node_is_for(built):
    assert rows(built, "quotes") == [("quotes", ["name"]), ("sales", ["purpose"])]
    first = find(built, "quotes").teams[0]
    assert first.kind == "division" and first.snippet == "Pricing pages we send to buyers"
    [web] = find(built, "web").teams
    assert (web.node_id, web.kind, web.matched_on, web.address, web.snippet) == ("web", "department", ["name"], "Web", "")


def test_a_task_title_and_a_task_outcome_find_the_team_and_say_which(built):
    task(built, 1, "web", title="Cafe landing page", outcome="Built index.html with a booking form")
    assert rows(built, "landing") == [("web", ["task"])]
    assert rows(built, "booking") == [("web", ["outcome"])]
    [hit] = find(built, "booking form").teams
    assert hit.snippet == "Built index.html with a booking form"
    assert rows(built, "booking landing") == []                                   # every word must be in ONE field


def test_a_task_scoped_to_a_live_division_belongs_to_the_division_and_one_of_a_merged_division_to_its_team(built):
    task(built, 1, "sales", title="Chase warm buyers", scope="leads")
    assert rows(built, "warm buyers") == [("leads", ["task"])]
    built.apply(merge_op("quotes", "leads"), approved=True)
    assert rows(built, "warm buyers") == [("sales", ["task"])]


def test_the_words_are_matched_without_regard_to_case_and_all_of_them_must_be_there(built):
    assert rows(built, "PRICING PAGES") == [("quotes", ["purpose"])]
    assert rows(built, "pricing flowers") == []
    assert rows(built, "  pricing   pages  ") == [("quotes", ["purpose"])]


# ---- what is not a search ----------------------------------------------------------------------------------------------------------

def test_one_character_is_not_a_search_and_two_are(built):
    assert MIN_CHARS == 2
    for q in ("", " ", "w", " w ", None):
        out = find(built, q)
        assert (out.teams, out.counts, out.truncated) == ([], {"department": 0, "division": 0}, False)
    assert [r.node_id for r in find(built, "we").teams]                          # 'we' is in 'Web' ... and matches by substring
    assert words_of("a b") == [] and words_of("a bc") == ["a", "bc"] and len(words_of("one two three four five six seven")) == 5


def test_a_merged_away_division_is_never_returned_and_the_root_is_not_a_team(built):
    assert "leads" in [r.node_id for r in find(built, "leads").teams]
    built.apply(merge_op("quotes", "leads"), approved=True)
    assert "leads" not in [r.node_id for r in find(built, "leads").teams]
    assert "root" not in [r.node_id for r in find(built, "root").teams]
    task(built, 2, "sales", title="Leads follow up", scope="leads")                # its division is gone: the task belongs to the team
    assert rows(built, "follow") == [("sales", ["task"])]


# ---- the order ----------------------------------------------------------------------------------------------------------------------

def test_a_name_ranks_above_a_purpose_above_a_task_above_an_outcome(db, settings, clock, events):
    env = Env(db, settings, clock, events)
    env.apply(dept_op("$o", "Orchard notes"), dept_op("$p", "Plain"), dept_op("$t", "Timber"), dept_op("$n", "Name apple"))
    env.apply(rename_op("plain", purpose="we sell apple jam"))
    task(env, 1, "timber", title="Pick apple crates")
    task(env, 2, "orchard-notes", title="Counting", outcome="Counted the apple trees")
    assert rows(env, "apple") == [("name-apple", ["name"]), ("plain", ["purpose"]), ("timber", ["task"]), ("orchard-notes", ["outcome"])]


def test_a_node_that_matches_in_several_fields_lists_them_best_first(built):
    task(built, 1, "sales", title="Quotes review", outcome="Quotes sent")
    [hit] = [r for r in find(built, "quotes").teams if r.node_id == "sales"]
    assert hit.matched_on == ["purpose", "task", "outcome"] and hit.kind == "department"


def test_among_equal_ranks_a_name_that_starts_with_the_word_comes_first(db, settings, clock, events):
    env = Env(db, settings, clock, events)
    env.apply(dept_op("$a", "Fresh bread"), dept_op("$b", "Bread shop"))
    assert [r.node_id for r in find(env, "bread").teams] == ["bread-shop", "fresh-bread"]


def test_the_rows_are_limited_and_the_counts_and_the_truncated_flag_say_how_many_there_were(db, settings, clock, events):
    env = Env(db, settings, clock, events)
    env.apply(dept_op("$s", "Shop"))
    for i in range(LIMIT + 3):
        env.apply(add_op(f"$d{i}", "division", f"Counter number{i:02d}", "shop"))
    out = find(env, "counter")
    assert len(out.teams) == LIMIT and out.truncated is True and out.counts == {"department": 0, "division": LIMIT + 3}
    small = find(env, "counter", limit=3)
    assert len(small.teams) == 3 and small.truncated is True
    assert find(env, "shop").truncated is False


def test_the_read_writes_nothing(built):
    task(built, 1, "web", title="Cafe landing page")
    before = snapshot(built)
    find(built, "cafe")
    find(built, "pricing")
    assert snapshot(built) == before
