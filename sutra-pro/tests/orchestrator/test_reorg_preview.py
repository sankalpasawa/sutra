"""ReorgPreview (gap package chart-insight): what a merge or a split will do, said before the owner answers.

`describe` runs the library's own `apply_change` and `carry_links` on the pending change and writes the consequences as sentences made by
code. These tests pin the words the owner reads, that only what THIS change adds is said, and that nothing is written (the old test 18:
a simulation does not mutate the registry)."""
import pytest
from factories_org import dept_op, div_op, make_chart, merge_op, move_op, new_node, rename_op, split_op
from orchestrator.test_chart_store import Env

from sutra_app.library.gate import GATE
from sutra_app.orchestrator.chart_health import items_of, overlap_pairs
from sutra_app.orchestrator.records import ChatMessage
from sutra_app.orchestrator.reorg_preview import DEPTH_WARN, LINE_CHARS, MAX_LINES, ReorgPreview, card_lines


@pytest.fixture
def built(db, settings, clock, events):
    return Env(db, settings, clock, events).build()


@pytest.fixture
def bare(db, settings, clock, events):
    """A chart with one team, Sales, and nothing under it."""
    env = Env(db, settings, clock, events)
    env.apply(dept_op("$s", "Sales"))
    return env


def preview(env, *ops, **kw):
    return ReorgPreview(env.db).describe(env.change(*ops, **kw).model, env.head())


def node_named(env, name: str) -> str:
    return next(n.id for n in env.head().nodes if n.name == name)


def talk(env, node_id: str, n: int) -> str:
    """`n` messages in the active chat of a node; returns the session id."""
    session = env.session_of(node_id)
    with env.db.tx() as tx:
        for i in range(n):
            msg = GATE.check("chat_message", ChatMessage(kind="text", session_id=session, role="user", who="user", text=f"line {i}", at=tx.now()), ctx=tx.ctx)
            env.chats.post(tx, session, msg)
    return session


def snapshot(env) -> dict:
    conn = env.db.conn()
    names = [r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {n: [tuple(r) for r in conn.execute(f'SELECT * FROM "{n}" ORDER BY rowid')] for n in names if not n.startswith("chat_search")}


def task(env, n: int, dept: str, status: str = "running", *, scope: str | None = None, title: str | None = None) -> str:
    task_id = f"tsk_{n:012x}"
    env.sql("INSERT INTO tasks(id, dept_id, scope_node_id, title, user_text, status, run_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
            task_id, dept, scope, title or f"Task {n}", "u", status, f"j2-20261104-1000{n:02d}-aaaa" if status in ("starting", "running", "waiting_user") else None, n)
    return task_id


# ---- a merge ----------------------------------------------------------------------------------------------------------------------

def test_a_merge_says_which_chat_stays_open_and_which_becomes_read_only_history_with_counts(built):
    talk(built, "leads", 6)
    talk(built, "quotes", 14)
    out = preview(built, merge_op("quotes", "leads"))
    assert "The chat of Leads (6 messages) becomes read-only history under Quotes." in out.lines
    assert "The chat of Quotes (14 messages) stays open." in out.lines
    assert out.lines[-1] == "Nothing is running in Leads."
    assert out.notes == []


def test_one_message_is_not_plural(built):
    talk(built, "leads", 1)
    assert "The chat of Leads (1 message) becomes read-only history under Quotes." in preview(built, merge_op("quotes", "leads")).lines


def test_a_merge_counts_the_step_nodes_that_move_and_names_the_children_that_come_along(built):
    built.apply(div_op("$deep", "Deep Dive", "leads"))
    done = task(built, 1, "sales", "done", scope="leads")
    for n in (1, 2):
        built.sql("INSERT INTO graph_nodes(id, kind, department_id, parent_id, label, body, sha256, ts, task_id, step_ref) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  f"step-{n}", "step", "sales", "leads", f"Step {n}", "{}", "x", 1, done, f"W-{n}")
    out = preview(built, merge_op("quotes", "leads"))
    assert "2 step nodes of Leads would move to Quotes." in out.lines
    assert "Deep Dive would move under Quotes." in out.lines


def test_older_chats_of_the_merged_division_are_said_to_follow_it(built):
    for sid in ("cs_aaaaaaaaaaaa", "cs_bbbbbbbbbbbb"):
        built.sql("INSERT INTO chat_sessions(id, node_id, kind, title, writable, status, created_at, updated_at, filed_under) VALUES (?,?,?,?,?,?,?,?,?)",
                  sid, "leads", "division", "Earlier", 0, "archived", 1, 1, "leads")
    assert "2 older chats of Leads are filed under Quotes too." in preview(built, merge_op("quotes", "leads")).lines


def test_a_survivor_with_no_open_chat_takes_the_chat_of_the_merged_division(built):
    """carry_links: a survivor with no active session takes the first merged-away one (`move`), so that chat stays open under the survivor."""
    built.sql("UPDATE chat_sessions SET status = 'archived', writable = 0 WHERE node_id = 'quotes'")
    talk(built, "leads", 4)
    out = preview(built, merge_op("quotes", "leads"))
    assert "The chat of Leads (4 messages) moves to Quotes and stays open." in out.lines
    assert not any("read-only history" in line for line in out.lines)


def test_a_busy_division_says_a_yes_would_be_refused_and_never_says_nothing_is_running(built):
    task(built, 1, "sales", scope="leads", title="Quote follow-ups")
    out = preview(built, merge_op("quotes", "leads"))
    assert out.notes == ["Leads is busy with Quote follow-ups: a yes would be refused until it finishes"]
    assert not any(line.startswith("Nothing is running") for line in out.lines)


def test_a_task_of_another_division_does_not_make_this_one_busy(built):
    task(built, 1, "web", scope="menu", title="Elsewhere")
    out = preview(built, merge_op("quotes", "leads"))
    assert out.notes == [] and out.lines[-1] == "Nothing is running in Leads."


def test_a_change_planned_on_an_older_chart_says_the_chart_moved_on(built):
    change = built.change(merge_op("quotes", "leads"))
    built.apply(rename_op("menu", name="Dishes"))
    out = ReorgPreview(built.db).describe(change.model, built.head())
    assert out.lines == [] and out.notes == ["The chart changed since you were asked: a yes would be refused"]


def test_a_change_the_library_refuses_is_one_sentence_not_an_error(built):
    out = preview(built, rename_op("quotes", name="Leads"))              # two divisions of Sales named Leads
    assert out.lines == [] and len(out.notes) == 1 and out.notes[0].startswith("A yes would be refused now: ")


# ---- a split ----------------------------------------------------------------------------------------------------------------------

def test_a_split_keeps_its_chat_and_the_new_divisions_start_empty(built):
    talk(built, "leads", 9)
    out = preview(built, split_op("leads", [new_node("$w", "division", "Warm Leads", "sales"), new_node("$c", "division", "Cold Leads", "sales")]))
    assert "The chat of Leads (9 messages) stays open." in out.lines
    assert "Warm Leads and Cold Leads start with an empty chat." in out.lines
    assert out.lines[-1] == "Nothing is running in Leads."


def test_a_split_that_moves_a_child_into_a_part_says_which(built):
    built.apply(div_op("$deep", "Deep Dive", "leads"))
    out = preview(built, split_op("leads", [new_node("$w", "division", "Warm Leads", "sales")], moves=[(node_named(built, "Deep Dive"), "$w")]))
    assert "Deep Dive would move into Warm Leads." in out.lines


def test_one_new_division_starts_with_an_empty_chat_in_the_singular(built):
    out = preview(built, split_op("leads", [new_node("$w", "division", "Warm Leads", "sales")]))
    assert "Warm Leads starts with an empty chat." in out.lines


# ---- the result: only what this change adds ---------------------------------------------------------------------------------------

STAGES = ("Alpha stage", "Beta phase", "Gamma step", "Delta tier")          # no word in common, so adding them is never a reuse


def descend(env, count: int) -> str:
    """A straight line of `count` divisions below Sales; returns the id of the deepest."""
    parent = "sales"
    for i, name in enumerate(STAGES[:count]):
        env.apply(div_op(f"$d{i}", name, parent))
        parent = node_named(env, name)
    return parent


def test_a_sibling_that_would_now_look_alike_is_said_and_a_pair_that_already_did_is_not_repeated(bare):
    bare.apply(div_op("$a", "Price list", "sales"), div_op("$b", "Price list page", "sales"), div_op("$q", "Quotes", "sales"))
    known = overlap_pairs(*items_of(bare.head()))
    assert [(a.name, b.name) for a, b, _ in known] == [("Price list", "Price list page")]            # true before the change
    out = preview(bare, rename_op(node_named(bare, "Quotes"), name="Price list today"))
    assert "Price list and Price list today would look alike (67% of their words)." in out.notes
    assert "Price list page and Price list today would look alike (50% of their words)." in out.notes
    assert not any(note.startswith("Price list and Price list page") for note in out.notes)
    assert preview(bare, rename_op(node_named(bare, "Quotes"), name="Offers")).notes == []


def test_a_node_and_its_own_ancestor_are_never_said_to_look_alike(bare):
    bare.apply(div_op("$m", "Menu", "sales"), div_op("$mi", "Menu items", "$m"))                  # one change: the reuse rule compares with live nodes only
    assert overlap_pairs(*items_of(bare.head())) == []
    assert preview(bare, rename_op(node_named(bare, "Menu items"), name="Menu items list")).notes == []


def test_a_chart_that_becomes_deeper_is_said_only_when_the_change_makes_it_deeper(bare):
    deepest = descend(bare, 3)                                                  # Sales is at depth 1; the three divisions at 2, 3 and 4
    bare.apply(div_op("$x", "Side", "sales"))
    out = preview(bare, move_op(node_named(bare, "Side"), deepest))             # Side would sit at depth 5
    assert DEPTH_WARN == 5 and out.notes == ["The chart would be 5 levels deep (6 is the most)."]
    assert out.lines == ["Side moves from Sales to Gamma step.", "Nothing is running in Side."]
    assert preview(bare, rename_op(node_named(bare, "Side"), name="Side step")).notes == []        # not deeper than it is


def test_a_deep_chart_that_stays_as_deep_says_nothing(bare):
    descend(bare, 4)                                                            # depth 5 already
    bare.apply(div_op("$x", "Side", "sales"))
    assert preview(bare, move_op(node_named(bare, "Side"), node_named(bare, "Gamma step"))).notes == []



# ---- nothing is written and the card fits ------------------------------------------------------------------------------------------

def test_describe_writes_nothing(built):
    talk(built, "leads", 3)
    before = snapshot(built)
    preview(built, merge_op("quotes", "leads"))
    preview(built, split_op("leads", [new_node("$w", "division", "Warm", "sales")]))
    ReorgPreview(built.db).describe(built.change(merge_op("quotes", "leads")).model, make_chart({"sales": {}}))     # a chart it does not match: refused, no write
    assert snapshot(built) == before


def test_the_card_puts_the_notes_first_and_every_line_fits(built):
    lines = card_lines(preview(built, merge_op("quotes", "leads")))
    assert 0 < len(lines) <= MAX_LINES and all(0 < len(x) <= LINE_CHARS for x in lines)
    task(built, 1, "sales", scope="leads", title="Quote follow-ups")
    assert card_lines(preview(built, merge_op("quotes", "leads")))[0].startswith("Leads is busy with")
