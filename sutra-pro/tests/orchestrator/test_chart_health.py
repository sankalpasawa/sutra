"""ChartHealth (gap package chart-insight): what has drifted in the chart, in names, read-only.

The old studio's simulate() findings, re-expressed over Pro's chart: two live nodes of one kind that look alike (ancestors exempt), a node whose
purpose says nothing, a team nobody uses, every age measured from the one `now` the caller passes, and a read that writes nothing."""
import pytest
from factories_org import add_op, dept_op, div_op
from orchestrator.test_chart_store import Env

from sutra_app.library.gate import GATE
from sutra_app.orchestrator.chart_health import (
    MAX_NOTES, OVERLAP_WARN, QUIET_DAYS, ChartHealth, Item, labels_of, overlap_pairs, related, thin_purpose,
)
from sutra_app.orchestrator.records import ChatMessage

DAY = 86400


@pytest.fixture
def bare(db, settings, clock, events):
    """One team, Sales, and nothing under it."""
    env = Env(db, settings, clock, events)
    env.apply(dept_op("$s", "Sales"))
    return env


def notes(env, now: int):
    return ChartHealth(env.db).notes(now)


def kinds(out) -> list[str]:
    return [n.kind for n in out.notes]


def born(env, node_id: str) -> int:
    return env.one("SELECT ts FROM org_nodes WHERE id = ?", node_id)


def task(env, n: int, dept: str, status: str = "done", *, created: int, ended: int | None = None, title: str | None = None) -> None:
    env.sql("INSERT INTO tasks(id, dept_id, title, user_text, status, run_id, created_at, ended_at) VALUES (?,?,?,?,?,?,?,?)",
            f"tsk_{n:012x}", dept, title or f"Task {n}", "u", status, f"j2-20261104-1000{n:02d}-aaaa" if status in ("starting", "running", "waiting_user") else None, created, ended)


def snapshot(env) -> dict:
    conn = env.db.conn()
    names = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {n: [tuple(r) for r in conn.execute(f'SELECT * FROM "{n}" ORDER BY rowid')] for n in names if not n.startswith("chat_search")}


# ---- overlap ----------------------------------------------------------------------------------------------------------------------

def test_two_divisions_at_forty_percent_are_flagged_with_the_words_to_merge_them(bare):
    bare.apply(div_op("$a", "Alpha beta gamma", "sales"), div_op("$b", "Alpha beta delta epsilon", "sales"))        # 2 of 5 words: 0.40
    out = notes(bare, now=born(bare, "sales"))
    [note] = [n for n in out.notes if n.kind == "overlap"]
    assert OVERLAP_WARN == 0.40
    assert note.words == "Alpha beta gamma and Alpha beta delta epsilon look alike (40% of their words)"
    assert note.say == "merge Alpha beta delta epsilon into Alpha beta gamma"
    assert [n.label for n in note.nodes] == ["Alpha beta gamma", "Alpha beta delta epsilon"]


def test_a_pair_just_under_the_line_is_not_flagged(bare):
    bare.apply(div_op("$a", "Alpha beta gamma", "sales"), div_op("$b", "Alpha delta epsilon zeta", "sales"))        # 1 of 6 words
    assert [n for n in notes(bare, 0).notes if n.kind == "overlap"] == []


def test_a_parent_and_its_child_are_not_flagged_however_alike_they_are(bare):
    bare.apply(div_op("$m", "Menu pages", "sales"), div_op("$mi", "Menu pages list", "$m"))
    assert [n for n in notes(bare, 0).notes if n.kind == "overlap"] == []
    items = [Item("a", "division", "Menu pages", "x"), Item("b", "division", "Menu pages list", "x")]
    assert related({"a": "root", "b": "a"}, "a", "b") and related({"a": "root", "b": "a"}, "b", "a")
    assert overlap_pairs(items, {"a": "root", "b": "a"}) == []
    assert len(overlap_pairs(items, {"a": "root", "b": "root"})) == 1                 # siblings with the same words are flagged


def test_two_teams_that_look_alike_are_flagged_with_no_sentence_to_say_because_a_team_is_never_merged(bare):
    bare.apply(dept_op("$a", "Sales pipeline team"), dept_op("$b", "Pipeline sales team"))
    [note] = [n for n in notes(bare, 0).notes if n.kind == "overlap"]
    assert note.say == "" and note.words == "Sales pipeline team and Pipeline sales team look alike (100% of their words)"


def test_a_team_and_a_division_are_never_compared(bare):
    bare.apply(div_op("$d", "Sales", "sales"))                                    # a division named like its own team
    assert [n for n in notes(bare, 0).notes if n.kind == "overlap"] == []


def test_two_nodes_with_the_same_name_in_different_places_are_told_apart_by_their_address(bare):
    bare.apply(dept_op("$b", "Bakery"))
    bare.apply(add_op("$m1", "division", "Menu", "sales", "cafe menu"), add_op("$m2", "division", "Menu", "bakery", "cafe menu"))
    [note] = [n for n in notes(bare, 0).notes if n.kind == "overlap"]
    assert note.words == "Sales > Menu and Bakery > Menu look alike (100% of their words)"
    assert labels_of([Item("a", "division", "Menu", ""), Item("b", "division", "Pages", "")], {}) == {"a": "Menu", "b": "Pages"}


# ---- no purpose --------------------------------------------------------------------------------------------------------------------

def test_an_empty_purpose_and_a_purpose_that_only_repeats_the_name_are_flagged(bare):
    bare.apply(div_op("$e", "Reviews", "sales"), add_op("$r", "division", "Support desk", "sales", "support desk"),
               add_op("$g", "division", "Quotes", "sales", "Prices we send to leads"))
    got = {n.nodes[0].label: n.words for n in notes(bare, 0).notes if n.kind == "no_purpose"}
    assert got == {"Sales": "Sales has no purpose written", "Reviews": "Reviews has no purpose written",
                   "Support desk": "The purpose of Support desk only repeats its name"}
    [say] = {n.say for n in notes(bare, 0).notes if n.words == "Reviews has no purpose written"}
    assert say == "change the purpose of Reviews to ..."
    assert (thin_purpose(Item("a", "division", "Quotes", "Prices we send")), thin_purpose(Item("a", "division", "Quotes", "  "))) == ("", "empty")


# ---- quiet -------------------------------------------------------------------------------------------------------------------------

def test_a_team_idle_for_ninety_days_is_flagged_by_an_injected_clock_and_not_ten_days_after_its_last_task(bare):
    bare.sql("UPDATE org_nodes SET purpose = 'Sells things to leads' WHERE id = 'sales'")
    start = born(bare, "sales")
    task(bare, 1, "sales", created=start, ended=start + 3600)
    last = start + 3600
    quiet = notes(bare, now=last + 90 * DAY)
    [note] = [n for n in quiet.notes if n.kind == "quiet"]
    assert note.words == "Sales has had nothing for 90 days" and note.say == "" and [n.id for n in note.nodes] == ["sales"]
    assert [n for n in notes(bare, now=last + 10 * DAY).notes if n.kind == "quiet"] == []
    assert [n for n in notes(bare, now=last + QUIET_DAYS * DAY - 1).notes if n.kind == "quiet"] == []
    assert len([n for n in notes(bare, now=last + QUIET_DAYS * DAY).notes if n.kind == "quiet"]) == 1


def test_a_chat_message_or_an_unfinished_task_means_the_team_is_in_use(bare):
    start = born(bare, "sales")
    now = start + 200 * DAY
    assert len([n for n in notes(bare, now).notes if n.kind == "quiet"]) == 1                            # born 200 days ago, never used
    session = bare.session_of("sales")
    with bare.db.tx() as tx:
        msg = GATE.check("chat_message", ChatMessage(kind="text", session_id=session, role="user", who="user", text="hello", at=start + 190 * DAY), ctx=tx.ctx)
        bare.chats.post(tx, session, msg)
    assert [n for n in notes(bare, now).notes if n.kind == "quiet"] == []                                # a message 10 days ago
    assert len([n for n in notes(bare, start + 260 * DAY).notes if n.kind == "quiet"]) == 1             # and 70 days after that it is quiet again
    task(bare, 2, "sales", "queued", created=start + 1)
    assert [n for n in notes(bare, start + 900 * DAY).notes if n.kind == "quiet"] == []                  # something unfinished: never quiet


def test_a_new_team_is_not_quiet_and_the_oldest_quiet_team_comes_first(bare):
    bare.apply(dept_op("$w", "Web"))
    old = born(bare, "sales")
    bare.sql("UPDATE org_nodes SET ts = ? WHERE id = 'sales'", old - 30 * DAY)
    bare.sql("UPDATE org_nodes SET ts = ? WHERE id = 'web'", old)
    out = [n for n in notes(bare, old + 70 * DAY).notes if n.kind == "quiet"]
    assert [n.nodes[0].label for n in out] == ["Sales", "Web"]
    assert [n.words for n in out] == ["Sales has had nothing for 100 days", "Web has had nothing for 70 days"]
    assert [n for n in notes(bare, old + 10 * DAY).notes if n.kind == "quiet"] == []


# ---- the read ----------------------------------------------------------------------------------------------------------------------

def test_a_chart_with_nothing_flagged_has_no_notes(bare):
    bare.sql("UPDATE org_nodes SET purpose = 'Sells things to leads' WHERE id = 'sales'")
    out = notes(bare, now=born(bare, "sales") + DAY)
    assert (out.notes, out.total) == ([], 0)


def test_the_notes_are_capped_and_the_total_is_counted(bare):
    for i in range(MAX_NOTES + 5):
        bare.apply(div_op(f"$d{i}", f"Division number{i:02d}", "sales"))
    out = notes(bare, now=born(bare, "sales"))
    assert len(out.notes) == MAX_NOTES and out.total == MAX_NOTES + 6                      # 25 divisions and Sales, each with no purpose


def test_the_read_writes_nothing_and_the_root_and_merged_away_nodes_are_never_named(bare):
    bare.apply(div_op("$a", "Alpha beta gamma", "sales"), div_op("$b", "Alpha beta delta epsilon", "sales"))
    before = snapshot(bare)
    out = notes(bare, now=born(bare, "sales") + 400 * DAY)
    assert snapshot(bare) == before
    assert "root" not in {n.id for note in out.notes for n in note.nodes}
    bare.sql("UPDATE org_nodes SET state = 'archived' WHERE id = 'alpha-beta-gamma'")
    assert "alpha-beta-gamma" not in {n.id for note in notes(bare, 0).notes for n in note.nodes}
