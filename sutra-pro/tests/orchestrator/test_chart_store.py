"""ChartStore (ORCH-5): bootstrap, the apply transaction, the approval flow, the change log and the projections.

`Env` builds a real database with the chart store, the graph store and the chat store, bootstrapped; the other ORCH-5 test files
import it from here."""
import json
import sqlite3

import pytest
from factories_node import toy_specs
from factories_org import (
    add_op, dept_op, div_op, make_change, merge_op, move_op, new_node, rename_op, split_op,
)

from sutra_app.library.gate import GATE, Checked
from sutra_app.library.node import check_graph, derive_edges
from sutra_app.library.types import FUNCTIONS
from sutra_app.orchestrator.chart import GREETING, ChangeFailed, ChartStore
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.errors import AlreadyDecided, AppError, NotFound
from sutra_app.orchestrator.graph import GraphStore
from sutra_app.orchestrator.models import ChangeContext
from sutra_app.orchestrator.testing import FakeIds


class Env:
    """A bootstrapped chart: ChartStore + GraphStore + ChatStore over one database in a temp data dir."""

    def __init__(self, db, settings, clock, events) -> None:
        self.db, self.settings, self.events = db, settings, events
        self.graph = GraphStore(db, specs=toy_specs())
        self.chats = ChatStore(db)
        self.chart = ChartStore(db, graph=self.graph, chats=self.chats, data_dir=settings.data_dir, ids=FakeIds(clock))
        assert self.chart.bootstrap() is True
        self.n = 0
        events.batches.clear()

    # ---- building and applying changes -----------------------------------------------------------------------------------

    def change(self, *ops, reuses=(), reason: str = "test change", base: int | None = None, task: str | None = None) -> Checked:
        self.n += 1
        head = self.chart.head().model
        made = make_change(head, *ops, reuses=reuses, reason=reason, base_revision=base, task_id=task or f"req-{self.n}",
                           id=self.chart.next_change_id())
        return GATE.check("chart_change", made)

    def ctx(self, title: str = "Coffee shop landing page", message_id: int = 1) -> ChangeContext:
        return ChangeContext(session_id="cs_org", message_id=message_id, request_id=f"req-{message_id}", request_title=title)

    def apply(self, *ops, actor: str = "chat_agent", title: str = "Coffee shop landing page", approved: bool = False, plan=None, **kw):
        return self.chart.apply(self.change(*ops, **kw), actor=actor, ctx=self.ctx(title), plan=plan, approved=approved)

    def head(self):
        return self.chart.head().model

    def sql(self, text: str, *args):
        return self.db.conn().execute(text, args)

    def one(self, text: str, *args):
        row = self.sql(text, *args).fetchone()
        return row[0] if row is not None else None

    def session_of(self, node_id: str) -> str:
        return self.one("SELECT id FROM chat_sessions WHERE node_id = ? AND status = 'active'", node_id)

    def build(self) -> "Env":
        """web (menu), sales (leads, quotes) through the real apply path."""
        self.apply(dept_op("$sales", "Sales"), dept_op("$web", "Web"))
        self.apply(div_op("$leads", "Leads", "sales"), div_op("$quotes", "Quotes", "sales"), div_op("$menu", "Menu", "web"))
        self.events.batches.clear()
        return self


@pytest.fixture
def env(db, settings, clock, events):
    return Env(db, settings, clock, events)


@pytest.fixture
def built(env):
    return env.build()


def assert_graph_matches(env: Env) -> None:
    """I1, I2 and I7: every graph node has exactly one active session it names, the graph mirrors the chart, no contains edge."""
    conn = env.db.conn()
    nodes = [env.graph.get(r["id"]) for r in conn.execute("SELECT id FROM graph_nodes ORDER BY rowid")]
    for node in nodes:
        active = [r["id"] for r in conn.execute("SELECT id FROM chat_sessions WHERE node_id = ? AND status = 'active'", (node.id,))]
        assert active == [node.chat_session_id], node.id
    assert check_graph(env.head(), nodes, derive_edges(env.head(), nodes)) == []
    assert conn.execute("SELECT count(*) FROM graph_edges WHERE kind = 'contains'").fetchone()[0] == 0


def assert_projection_equals_head(env: Env) -> None:
    head = env.head()
    live = {r["id"]: r for r in env.sql("SELECT id, kind, name, purpose FROM org_nodes WHERE state = 'active'")}
    assert set(live) == {n.id for n in head.nodes}
    for node in head.nodes:
        assert (live[node.id]["kind"], live[node.id]["name"], live[node.id]["purpose"]) == (node.kind, node.name, node.purpose)
    edges = {(r["parent_id"], r["child_id"]): r["position"] for r in env.sql("SELECT parent_id, child_id, position FROM org_edges")}
    assert set(edges) == {(e.parent, e.child) for e in head.edges}
    for parent in {p for p, _ in edges}:
        sibling_order = [n.id for n in head.nodes if head.parent_of(n.id) == parent]
        assert [c for (p, c) in sorted((e for e in edges if e[0] == parent), key=lambda e: edges[e])] == sibling_order


def assert_shas_chain(env: Env) -> None:
    """I5: after_sha of each applied row is the before_sha of the next applied row; the last is the head's sha."""
    rows = env.sql("SELECT before_sha, after_sha FROM chart_changes WHERE status = 'applied' ORDER BY seq").fetchall()
    for earlier, later in zip(rows, rows[1:]):
        assert earlier["after_sha"] == later["before_sha"]
    assert rows[-1]["after_sha"] == env.chart.head().sha256


# ---- bootstrap ------------------------------------------------------------------------------------------------------------------

def test_bootstrap_makes_the_root_the_org_chat_the_greeting_and_the_first_change(env):
    head = env.chart.head()
    assert [n.id for n in head.model.nodes] == ["root"] and head.model.revision == 1
    assert env.one("SELECT count(*) FROM org_charts") == 1 and env.one("SELECT sha256 FROM org_charts") == head.sha256
    row = env.sql("SELECT * FROM chart_changes").fetchone()
    assert (row["seq"], row["id"], row["kind"], row["actor"], row["status"], row["result_revision"], row["task_id"], row["task_title"]) == \
        (1, "chg-0001", "add", "system", "applied", 1, "req-0", "")
    assert row["summary"] == "Started the org chart" and row["after_sha"] == head.sha256 and row["before_sha"] == ""
    session = env.chats.session("cs_org")
    assert (session.node_id, session.kind, session.writable, session.title) == ("root", "org", True, "Sutra")
    assert [(m.who, m.text) for m in env.chats.messages("cs_org")] == [("sutra", GREETING)]
    assert env.one("SELECT value FROM meta WHERE key = 'bootstrapped_at'") is not None
    assert env.graph.get("root").chat_session_id == "cs_org"
    assert_graph_matches(env)


def test_bootstrap_twice_changes_nothing(env):
    before = (env.one("SELECT count(*) FROM chart_changes"), env.one("SELECT count(*) FROM chat_messages"), env.one("SELECT value FROM meta WHERE key = 'graph_version'"))
    assert env.chart.bootstrap() is False
    assert (env.one("SELECT count(*) FROM chart_changes"), env.one("SELECT count(*) FROM chat_messages"), env.one("SELECT value FROM meta WHERE key = 'graph_version'")) == before


def test_head_before_bootstrap_says_to_bootstrap(db, settings):
    store = ChartStore(db, graph=GraphStore(db, specs=toy_specs()), chats=ChatStore(db), data_dir=settings.data_dir)
    with pytest.raises(RuntimeError, match="bootstrap"):
        store.head()


# ---- add a department ------------------------------------------------------------------------------------------------------------

def test_adding_a_department_makes_its_row_folders_five_function_nodes_and_sessions(env, settings):
    result = env.apply(dept_op("$web", "Web"), add_op("$menu", "division", "Menu", "$web"))
    assert (result.status, result.decision, result.revision, result.added, result.ids_by_ref) == \
        ("applied", "add", 2, ["web", "menu"], {"$web": "web", "$menu": "menu"})
    assert result.summary == "Added the Web team and the Menu division"
    dept = json.loads(env.one("SELECT body FROM departments WHERE id = 'web'"))
    assert (dept["id"], dept["home_dir"]) == ("web", "departments/web")
    runs = settings.data_dir / "departments" / "web" / "runs"
    assert runs.is_dir() and oct(runs.stat().st_mode & 0o777) == "0o700" and oct(runs.parent.stat().st_mode & 0o777) == "0o700"
    for fn in FUNCTIONS:
        node = env.graph.get(f"web.{fn}")
        assert node.kind == fn and node.department_id == "web" and node.goal and node.state == "idle"
        session = env.chats.session(node.chat_session_id)
        assert (session.kind, session.writable, session.node_id, session.title) == ("function", False, f"web.{fn}", f"Web · {fn.capitalize()}")
    web, menu = env.graph.get("web"), env.graph.get("menu")
    assert (web.kind, web.parent_id, web.department_id, menu.parent_id, menu.department_id) == ("department", "root", "web", "web", "web")
    assert (env.chats.session(web.chat_session_id).kind, env.chats.session(web.chat_session_id).writable) == ("department", True)
    assert (env.chats.session(menu.chat_session_id).kind, env.chats.session(menu.chat_session_id).writable) == ("division", True)
    assert_graph_matches(env)
    assert_projection_equals_head(env)
    assert_shas_chain(env)


def test_the_change_row_keeps_before_and_after_shas_ops_and_the_task_title(env):
    before = env.chart.head().sha256
    env.apply(dept_op("$web", "Web"), title="Coffee shop landing page", reason="no team makes websites")
    row = env.sql("SELECT * FROM chart_changes WHERE seq = 2").fetchone()
    assert (row["id"], row["kind"], row["actor"], row["status"], row["base_revision"], row["result_revision"], row["task_title"], row["reason"]) == \
        ("chg-0002", "add", "chat_agent", "applied", 1, 2, "Coffee shop landing page", "no team makes websites")
    assert row["before_sha"] == before and row["after_sha"] == env.chart.head().sha256 != before
    assert json.loads(row["ops_json"])[0]["op"] == "add" and json.loads(row["body"])["id"] == "chg-0002"
    assert json.loads(row["result_json"]) == {"added": ["web"], "moved": [], "archived": [], "reused": []}
    assert (row["session_id"], row["message_id"]) == ("cs_org", 1)


def test_events_of_an_add_are_chart_changed_then_graph_updated_with_the_documented_keys(env):
    env.apply(dept_op("$web", "Web"))
    types = [e.type for e in env.events.events]
    assert types == ["chart.changed", "graph.updated"]
    data = env.events.events[0].data
    assert data == {"revision": 2, "version": 2, "change_id": "chg-0002", "kind": "add", "status": "applied", "added": ["web"], "moved": [],
                    "merged": [], "archived": [], "summary": "Added the Web team"}
    assert {n["id"] for n in env.events.events[1].data["nodes"]} >= {"web", "web.identity", "web.audit"}


def test_a_change_with_another_id_is_stored_under_the_assigned_one(env):
    change = GATE.check("chart_change", make_change(env.head(), dept_op("$web", "Web"), id="chg-0777"))
    result = env.chart.apply(change, actor="user", ctx=env.ctx())
    assert result.id == "chg-0002" and json.loads(env.one("SELECT body FROM chart_changes WHERE seq = 2"))["id"] == "chg-0002"


def test_ids_come_from_names_and_a_retired_id_is_never_given_again(built):
    result = built.apply(merge_op("quotes", "leads"), approved=True)
    assert result.archived == ["leads"]
    again = built.apply(div_op("$x", "Leads", "web"))
    assert again.added == ["leads-2"]


def test_a_department_name_without_letters_gets_an_id_that_fits_the_url_and_folder_rules(env, settings):
    result = env.apply(dept_op("$d", "3D printing"))
    assert result.added == ["department-3d-printing"]
    assert (settings.data_dir / "departments" / "department-3d-printing" / "runs").is_dir()


def test_a_node_made_and_merged_away_in_one_change_still_leaves_a_retired_row(built):
    result = built.apply(div_op("$tmp", "Temp", "web"), merge_op("menu", "$tmp"), approved=True)
    assert result.added == [] and result.archived == ["temp"]
    assert built.sql("SELECT state, merged_into FROM org_nodes WHERE id = 'temp'").fetchone()[:] == ("archived", "menu")
    assert built.graph.get("temp") is None
    assert built.apply(div_op("$t2", "Temp", "web")).added == ["temp-2"]


# ---- reuse ----------------------------------------------------------------------------------------------------------------------

def test_a_reuse_logs_a_row_keeps_the_chart_and_moves_the_graph_version(built):
    head, version = built.chart.head(), built.one("SELECT value FROM meta WHERE key = 'graph_version'")
    result = built.apply(reuses=["web"], reason="the web team can take it")
    assert (result.status, result.decision, result.revision, result.added) == ("applied", "reuse", head.model.revision, [])
    assert result.summary == "Reused Web"
    assert built.chart.head().sha256 == head.sha256 and built.one("SELECT count(*) FROM org_charts") == head.model.revision
    row = built.sql("SELECT * FROM chart_changes ORDER BY seq DESC LIMIT 1").fetchone()
    assert (row["kind"], row["status"], row["before_sha"], row["after_sha"]) == ("reuse", "applied", head.sha256, head.sha256)
    assert json.loads(row["result_json"])["reused"] == ["web"]
    assert int(built.one("SELECT value FROM meta WHERE key = 'graph_version'")) == int(version) + 1
    assert [e.type for e in built.events.events] == ["chart.changed", "graph.updated"]
    assert_shas_chain(built)


# ---- move, rename, merge, split -------------------------------------------------------------------------------------------------

def test_moving_a_division_changes_its_parent_department_and_note_but_not_its_chat(built):
    session = built.session_of("menu")
    result = built.apply(move_op("menu", "sales"))
    assert (result.moved, result.summary) == (["menu"], "Moved Menu under Sales")
    node = built.graph.get("menu")
    assert (node.parent_id, node.department_id, node.chat_session_id) == ("sales", "sales", session)
    assert built.chats.session(session).note == "Moved from Web to Sales"
    assert built.one("SELECT parent_id FROM org_edges WHERE child_id = 'menu'") == "sales"
    assert_graph_matches(built)
    assert_projection_equals_head(built)


def test_a_move_inside_the_same_department_is_automatic_and_the_subtree_follows(built):
    built.apply(div_op("$deep", "Deep", "leads"))
    built.apply(move_op("leads", "web"))
    assert built.graph.get("deep").department_id == "web" and built.graph.get("leads").department_id == "web"
    assert_graph_matches(built)


def test_a_rename_changes_the_chart_the_graph_label_the_session_title_and_the_function_titles(built, settings):
    built.apply(rename_op("web", name="Web Studio", purpose="Sites for shops"))
    assert built.graph.get("web").label == "Web Studio"
    assert built.sql("SELECT name, purpose FROM org_nodes WHERE id = 'web'").fetchone()[:] == ("Web Studio", "Sites for shops")
    assert built.chats.session(built.session_of("web")).title == "Web Studio"
    assert built.chats.session(built.session_of("web.audit")).title == "Web Studio · Audit"
    assert json.loads((settings.data_dir / "departments" / "web" / "department.json").read_text())["name"] == "Web Studio"
    assert built.apply(rename_op("web", name="Web Studio 2")).summary == "Renamed Web Studio to Web Studio 2"
    assert built.apply(rename_op("web", purpose="x")).summary == "Changed the purpose of Web Studio 2"


def test_a_merge_waits_for_the_owner_then_files_the_old_chat_under_the_survivor(built):
    leads_chat, quotes_chat = built.session_of("leads"), built.session_of("quotes")
    step_parent = "leads"
    built.sql("INSERT INTO tasks(id, dept_id, title, user_text, status, created_at) VALUES ('tsk_000000000001','sales','Old','u','done',1)")
    with built.db.tx() as tx:
        from factories_node import step as step_node
        from sutra_app.library.node import step_node_id
        model = step_node("tsk_000000000001", "task", step_parent, department_id="sales", chat_session_id=None)
        from sutra_app.orchestrator.nodes import ensure_node, node_init
        ensure_node(tx, node_init(model), graph=built.graph)
    step_id = step_node_id("tsk_000000000001", "task")
    waiting = built.apply(merge_op("quotes", "leads"), plan={"assignments": ["a1"]})
    assert (waiting.status, waiting.revision, waiting.summary) == ("pending_approval", None, "Merged Leads into Quotes")
    assert built.head().node("leads") is not None and built.graph.get("leads") is not None
    assert [c.id for c in built.chart.pending()] == [waiting.id]
    assert "chart.approval" in [e.type for e in built.events.events]
    stored = built.chart.record(waiting.id)
    assert stored.plan == {"assignments": ["a1"]} and stored.change.model.ops[0].op == "merge"
    built.events.batches.clear()
    result = built.chart.decide(waiting.id, True)
    assert (result.status, result.archived, result.revision) == ("applied", ["leads"], built.head().revision)
    assert built.graph.get("leads") is None                                       # the merged-away graph node is deleted
    assert built.graph.get(step_id).parent_id == "quotes"                          # its steps go to the survivor
    old = built.chats.session(leads_chat)
    assert (old.status, old.writable, old.note, old.filed_under, old.node_id) == ("archived", False, "Merged into Quotes", "quotes", "leads")
    survivor = built.chats.session(quotes_chat)
    assert (survivor.status, survivor.note) == ("active", "Took in Leads")
    assert built.graph.get("quotes").chat_session_id == quotes_chat
    assert built.sql("SELECT state, merged_into FROM org_nodes WHERE id = 'leads'").fetchone()[:] == ("archived", "quotes")
    assert built.sql("SELECT count(*) FROM org_edges WHERE child_id = 'leads'").fetchone()[0] == 0
    row = built.sql("SELECT status, result_revision FROM chart_changes WHERE id = ?", waiting.id).fetchone()
    assert tuple(row) == ("applied", built.head().revision)
    assert {"chart.changed", "needs_you.changed"} <= {e.type for e in built.events.events}
    assert_graph_matches(built)
    assert_projection_equals_head(built)
    assert_shas_chain(built)


def test_a_merge_moves_the_children_of_the_source_and_leaves_no_graph_row_for_it(built):
    built.apply(div_op("$deep", "Deep", "leads"))
    built.apply(merge_op("quotes", "leads"), approved=True)
    assert built.head().parent_of("deep") == "quotes" and built.graph.get("deep").parent_id == "quotes"
    assert built.sql("SELECT count(*) FROM graph_nodes WHERE id = 'leads'").fetchone()[0] == 0
    assert built.sql("SELECT count(*) FROM graph_edges WHERE from_id = 'leads' OR to_id = 'leads'").fetchone()[0] == 0


def test_a_chained_merge_refiles_the_first_archived_chat_under_the_final_survivor(built):
    built.apply(div_op("$extra", "Extra", "sales"))
    leads_chat, quotes_chat = built.session_of("leads"), built.session_of("quotes")
    built.apply(merge_op("quotes", "leads"), approved=True)
    built.apply(merge_op("extra", "quotes"), approved=True)
    assert built.chats.session(leads_chat).filed_under == "extra" and built.chats.session(quotes_chat).filed_under == "extra"
    assert built.sql("SELECT merged_into FROM org_nodes WHERE id = 'leads'").fetchone()[0] == "extra"
    assert built.chats.session(built.session_of("extra")).note == "Took in Quotes"
    assert built.graph.get("quotes") is None
    assert_graph_matches(built)


def test_three_sources_merged_at_once_keep_every_chat_and_name_them_all(built):
    built.apply(div_op("$a", "Alpha", "sales"), div_op("$b", "Beta", "sales"))
    sessions = {d: built.session_of(d) for d in ("leads", "alpha", "beta", "quotes")}
    built.apply(merge_op("quotes", "leads", "alpha", "beta"), approved=True)
    assert [built.chats.session(sessions[d]).status for d in ("leads", "alpha", "beta", "quotes")] == ["archived"] * 3 + ["active"]
    assert built.chats.session(sessions["quotes"]).note == "Took in Leads, Alpha, Beta"
    assert built.one("SELECT count(*) FROM chat_sessions") == built.one("SELECT count(*) FROM graph_nodes") + 3


def test_a_split_waits_keeps_the_node_and_its_chat_and_gives_each_part_a_node_and_a_chat(built):
    built.apply(div_op("$c1", "Cold", "leads"))
    chat = built.session_of("leads")
    op = split_op("leads", [new_node("$warm", "division", "Warm leads", "sales")], moves=[("cold", "$warm")])
    pending = built.apply(op)
    assert pending.status == "pending_approval" and pending.added == ["warm-leads"]
    assert built.graph.get("warm-leads") is None
    result = built.chart.decide(pending.id, True)
    assert (result.status, result.added, result.moved) == ("applied", ["warm-leads"], ["cold"])
    assert result.summary == "Split Leads into Leads and Warm leads"
    assert built.session_of("leads") == chat and built.graph.get("leads").chat_session_id == chat
    assert built.graph.get("warm-leads").parent_id == "sales" and built.session_of("warm-leads")
    assert built.graph.get("cold").parent_id == "warm-leads"
    assert_graph_matches(built)
    assert_projection_equals_head(built)


# ---- approval -------------------------------------------------------------------------------------------------------------------

def test_a_pending_change_keeps_its_plan_lists_and_touches_nothing(built):
    head, rows = built.chart.head().sha256, built.one("SELECT count(*) FROM chart_changes")
    result = built.apply(merge_op("quotes", "leads"), title="Merge them", plan={"resume": "t7"})
    assert (result.status, result.archived) == ("pending_approval", ["leads"])
    assert built.chart.head().sha256 == head and built.one("SELECT count(*) FROM chart_changes") == rows + 1
    row = built.sql("SELECT * FROM chart_changes WHERE id = ?", result.id).fetchone()
    assert (row["status"], row["result_revision"], row["after_sha"], row["task_title"]) == ("pending_approval", None, "", "Merge them")
    assert json.loads(row["plan_json"]) == {"resume": "t7"} and json.loads(row["result_json"])["archived"] == ["leads"]
    out = built.chart.pending()[0]
    assert (out.status, out.revision, out.archived) == ("pending_approval", None, ["leads"])


def test_approved_true_applies_a_merge_at_once(built):
    assert built.apply(merge_op("quotes", "leads"), approved=True).status == "applied"
    assert built.chart.pending() == []


def test_saying_no_rejects_the_row_and_changes_nothing(built):
    pending = built.apply(merge_op("quotes", "leads"))
    head = built.chart.head().sha256
    result = built.chart.decide(pending.id, False)
    assert (result.status, result.revision, result.archived) == ("rejected", None, ["leads"])
    assert built.chart.head().sha256 == head and built.graph.get("leads") is not None
    stored = built.chart.record(pending.id)
    assert stored.out.status == "rejected" and stored.violations[0]["code"] == "declined"
    assert built.chart.pending() == []


def test_a_second_decision_raises_already_decided_with_the_first_result(built):
    pending = built.apply(merge_op("quotes", "leads"))
    first = built.chart.decide(pending.id, True)
    with pytest.raises(AlreadyDecided) as info:
        built.chart.decide(pending.id, False)
    assert info.value.result.status == "applied" and info.value.result.revision == first.revision
    assert built.chart.record(pending.id).out.status == "applied"


def test_a_decision_on_an_unknown_change_is_not_found(built):
    with pytest.raises(NotFound):
        built.chart.decide("chg-0999", True)


def test_a_yes_after_the_chart_moved_on_rejects_with_the_reason(built):
    pending = built.apply(merge_op("quotes", "leads"))
    built.apply(rename_op("web", name="Web Studio"))
    result = built.chart.decide(pending.id, True)
    assert result.status == "rejected" and built.graph.get("leads") is not None
    assert "changed since" in built.chart.record(pending.id).violations[0]["message"]


def test_a_yes_when_a_task_now_holds_the_division_rejects_with_busy(built):
    pending = built.apply(merge_op("quotes", "leads"))
    built.sql("INSERT INTO tasks(id, dept_id, scope_node_id, title, user_text, status, run_id, created_at) VALUES ('tsk_000000000002','sales','leads','Hot','u','running','j2-20261104-100000-aaaa',1)")
    assert built.chart.decide(pending.id, True).status == "rejected"
    assert built.chart.record(pending.id).violations[0]["code"] == "busy"


def test_deciding_moves_the_needs_you_count(built):
    pending = built.apply(merge_op("quotes", "leads"))
    built.events.batches.clear()
    built.chart.decide(pending.id, False)
    assert [e.data["count"] for e in built.events.events if e.type == "needs_you.changed"] == [0]


# ---- stale, rules, failures ------------------------------------------------------------------------------------------------------

def test_a_stale_change_is_logged_as_stale_with_the_plan_it_names_and_nothing_is_applied(built):
    old = built.change(dept_op("$x", "Support"), move_op("menu", "sales"))
    built.apply(rename_op("web", name="Web Studio"))
    head = built.chart.head().sha256
    result = built.chart.apply(old, actor="chat_agent", ctx=built.ctx("Support please"))
    assert (result.status, result.revision, result.moved) == ("stale", None, ["menu"])
    assert built.chart.head().sha256 == head
    row = built.chart.record(result.id).out
    assert (row.status, row.revision, row.moved, row.added, row.task_title) == ("stale", None, ["menu"], [], "Support please")
    assert built.sql("SELECT after_sha FROM chart_changes WHERE id = ?", result.id).fetchone()[0] == ""
    assert_shas_chain(built)


def test_a_change_with_violations_raises_rules_and_stores_nothing(built):
    before = built.one("SELECT count(*) FROM chart_changes")
    with pytest.raises(AppError) as info:
        built.apply(div_op("$x", "Menu", "web"), move_op("web", "sales"))
    assert info.value.code == "rules" and info.value.status == 422
    codes = [v["code"] for v in info.value.details["violations"]]
    assert "duplicate_name" in codes or "reuse_candidate" in codes
    assert "move_not_division" in codes
    assert built.one("SELECT count(*) FROM chart_changes") == before


def test_a_folder_that_cannot_be_made_undoes_everything_and_logs_a_failed_row(built, settings):
    (settings.data_dir / "departments" / "support").write_bytes(b"in the way")
    before = {t: built.one(f"SELECT count(*) FROM {t}") for t in ("org_charts", "org_nodes", "org_edges", "departments", "graph_nodes", "chat_sessions", "chart_changes")}
    head = built.chart.head().sha256
    with pytest.raises(ChangeFailed) as info:
        built.apply(dept_op("$s", "Support"), title="Help desk")
    assert info.value.code == "internal" and info.value.message == "I could not save that. Nothing was changed."
    assert built.chart.head().sha256 == head
    after = {t: built.one(f"SELECT count(*) FROM {t}") for t in before}
    assert after == {**before, "chart_changes": before["chart_changes"] + 1}
    row = built.chart.record(info.value.change_id)
    assert (row.out.status, row.out.task_title, row.violations[0]["code"]) == ("failed", "Help desk", "failed")
    assert built.sql("SELECT count(*) FROM graph_nodes WHERE id LIKE 'support%'").fetchone()[0] == 0
    assert_shas_chain(built)


def test_a_sql_error_in_the_middle_undoes_the_folders_it_made_too(built, settings, monkeypatch):
    real = built.graph.put_node
    calls = []

    def broken(tx, node):
        calls.append(node.model.id)
        if node.model.id == "support.audit":
            raise sqlite3.OperationalError("disk I/O error")
        return real(tx, node)

    monkeypatch.setattr(built.graph, "put_node", broken)
    head = built.chart.head().sha256
    with pytest.raises(ChangeFailed):
        built.apply(dept_op("$s", "Support"))
    assert "support.audit" in calls and built.chart.head().sha256 == head
    assert not (settings.data_dir / "departments" / "support").exists()
    assert built.sql("SELECT count(*) FROM departments WHERE id = 'support'").fetchone()[0] == 0
    assert built.sql("SELECT count(*) FROM graph_nodes WHERE id LIKE 'support%'").fetchone()[0] == 0
    assert [e.type for e in built.events.events] == ["chart.changed"]             # the failure row's event only; no graph.updated


def test_a_failure_while_deciding_marks_the_pending_row_failed(built, settings, monkeypatch):
    built.apply(dept_op("$s", "Support"))
    pending = built.apply(merge_op("quotes", "leads"))
    monkeypatch.setattr(built.chart, "_project", lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError("boom")))
    with pytest.raises(ChangeFailed) as info:
        built.chart.decide(pending.id, True)
    assert info.value.change_id == pending.id and built.chart.record(pending.id).out.status == "failed"
    assert built.graph.get("leads") is not None


# ---- the change log ------------------------------------------------------------------------------------------------------------

def test_the_task_title_rule_context_then_the_reason_cut_to_sixty_then_empty_for_the_system(built):
    long_reason = "please " + "make the lovely web pages for the coffee shop " * 3
    user = built.chart.apply(built.change(reuses=["web"], reason=long_reason), actor="user", ctx=built.ctx(title=""))
    title = built.chart.record(user.id).out.task_title
    assert 0 < len(title) <= 60 and " ".join(long_reason.split()).startswith(title) and not title.endswith(" ")
    assert built.chart.history(0, 1)[0].task_title == ""                           # the bootstrap row: system
    named = built.apply(reuses=["web"], title="Menu board")
    assert built.chart.record(named.id).out.task_title == "Menu board"


def test_history_is_oldest_first_with_an_after_cursor_and_a_limit(built):
    rows = built.chart.history()
    assert [r.seq for r in rows] == [1, 2, 3] and rows[0].actor == "system" and rows[0].added == ["root"]
    assert [r.seq for r in built.chart.history(after=1, limit=1)] == [2]
    assert built.chart.history(after=3) == []
    assert len(built.chart.history(limit=10_000)) == 3 and len(built.chart.history(limit=0)) == 1
    # newest=True: the NEWEST `limit` rows above `after`, still oldest first (QA org-chat-teams: the log pane asked for the first 50 of a long log)
    assert [r.seq for r in built.chart.history(limit=2, newest=True)] == [2, 3]
    assert [r.seq for r in built.chart.history(after=1, limit=1, newest=True)] == [3]
    assert [r.seq for r in built.chart.history(after=0, limit=10, newest=True)] == [1, 2, 3] == [r.seq for r in built.chart.history()]
    assert built.chart.history(after=3, limit=5, newest=True) == [] and len(built.chart.history(limit=0, newest=True)) == 1
    two = rows[1]
    assert (two.id, two.decision, two.status, two.revision, two.added, two.task_id) == ("chg-0002", "add", "applied", 2, ["sales", "web"], "req-1")
    assert two.at.endswith("Z") and two.summary == "Added the Sales team and the Web team"


def test_the_list_fields_of_a_move_and_a_merge_are_node_ids(built):
    built.apply(move_op("menu", "sales"))
    built.apply(merge_op("quotes", "leads"), approved=True)
    rows = built.chart.history()
    assert (rows[-2].decision, rows[-2].moved, rows[-2].archived) == ("rearrange", ["menu"], [])
    assert (rows[-1].decision, rows[-1].moved, rows[-1].archived) == ("rearrange", [], ["leads"])


def test_the_view_has_parents_and_positions_among_siblings(built):
    view = built.chart.view()
    assert view.version == built.head().revision
    found = {n.id: (n.kind, n.parent_id, n.position) for n in view.nodes}
    assert found == {"root": ("root", None, 0), "sales": ("department", "root", 0), "web": ("department", "root", 1),
                     "leads": ("division", "sales", 0), "quotes": ("division", "sales", 1), "menu": ("division", "web", 0)}


def test_preview_changes_nothing_and_says_what_would_happen(built):
    rows, head = built.one("SELECT count(*) FROM chart_changes"), built.chart.head().sha256
    result = built.chart.preview(built.change(dept_op("$s", "Support")))
    assert (result.status, result.revision, result.added, result.ids_by_ref) == ("applied", 4, ["support"], {"$s": "support"})
    assert built.chart.preview(built.change(merge_op("quotes", "leads"))).status == "pending_approval"
    assert built.one("SELECT count(*) FROM chart_changes") == rows and built.chart.head().sha256 == head
    with pytest.raises(AppError) as info:
        built.chart.preview(built.change(move_op("web", "sales")))
    assert info.value.code == "rules"


def test_check_returns_all_violations_and_apply_refuses_what_is_not_checked(built):
    found = built.chart.check(built.change(move_op("web", "sales"), rename_op("nobody", name="X")))
    assert [v.code for v in found] == ["move_not_division", "unknown_node"]
    with pytest.raises(TypeError):
        built.chart.apply(built.head(), actor="user", ctx=built.ctx())
    with pytest.raises(TypeError):
        built.chart.check(GATE.check("org_chart", built.head()))
    with pytest.raises(ValueError):
        built.chart.apply(built.change(reuses=["web"]), actor="robot", ctx=built.ctx())


def test_the_org_projection_equals_the_head_after_a_run_of_changes(built):
    built.apply(rename_op("sales", purpose="Selling"))
    built.apply(move_op("menu", "sales"))
    built.apply(merge_op("quotes", "leads"), approved=True)
    built.apply(dept_op("$s", "Support"), div_op("$t", "Tier one", "$s"))
    built.apply(split_op("tier-one", [new_node("$t2", "division", "Tier two", "support")]), approved=True)
    assert_projection_equals_head(built)
    assert_graph_matches(built)
    assert_shas_chain(built)
    assert built.one("SELECT count(*) FROM org_nodes WHERE state = 'archived'") == 1
    assert built.one("SELECT count(*) FROM departments") == 3


def test_the_digest_and_the_assignment_check_are_served_by_the_store(built):
    text = built.chart.digest("a menu for the cafe")
    assert text.startswith("Org chart revision 3. Root id: root.") and "web | Web" in text and "  menu | Menu" in text
    assert built.chart.check_assignments([{"dept": "web", "scope": None, "follows": None}]) == []
    assert built.chart.check_assignments([{"dept": "nope", "scope": None, "follows": None}])[0].code == "bad_assignment"
    assert built.chart.classify(built.change(merge_op("quotes", "leads"))) == "approve"


# ---- the node linker ------------------------------------------------------------------------------------------------------------

def _structural(node_id: str, kind: str = "division", **over):
    from sutra_app.library.node import StructuralNode
    return StructuralNode(id=node_id, kind=kind, label=over.pop("label", node_id.title()), ts_created=5, ts_updated=5, **over)


def test_node_init_derives_the_session_kind_and_who_may_write(built):
    from sutra_app.library.node import new_function_node
    from sutra_app.orchestrator.nodes import WRITABLE_KINDS, node_init, session_kind
    root, dept, div = _structural("root", "root"), _structural("web", "department", department_id="web"), _structural("menu", department_id="web")
    fnode = new_function_node("web", "audit", toy_specs(), 1)
    inits = {n.id: node_init(n) for n in (root, dept, div, fnode)}
    assert {k: (v.writable, v.session_id, v.session_title) for k, v in inits.items()} == {
        "root": (True, "cs_org", "Root"), "web": (True, None, "Web"), "menu": (True, None, "Menu"), "web.audit": (False, None, "Audit")}
    assert [session_kind(k) for k in ("root", "department", "division", "step", *FUNCTIONS)] == ["org", "department", "division", "step", *["function"] * 5]
    assert WRITABLE_KINDS == ("root", "department", "division")
    assert node_init(div, title="Other", session_id="cs_00000000abcd").session_title == "Other"
    with pytest.raises(ValueError):
        session_kind("banana")


def test_ensure_node_makes_the_node_and_its_one_session_together_and_is_idempotent(built):
    from sutra_app.orchestrator.nodes import ensure_node, node_init
    spec = node_init(_structural("extra", department_id="web", parent_id="web"))
    with built.db.tx() as tx:
        out = ensure_node(tx, spec, graph=built.graph)
    assert (out.id, out.kind, out.status, out.dept_id, out.org_node_id) == ("extra", "division", "idle", "web", "extra")
    session = built.chats.session(out.chat_session_id)
    assert (session.node_id, session.kind, session.writable, session.status) == ("extra", "division", True, "active")
    version = built.one("SELECT value FROM meta WHERE key = 'graph_version'")
    built.events.batches.clear()
    with built.db.tx() as tx:
        again = ensure_node(tx, spec, graph=built.graph)
    assert again.chat_session_id == out.chat_session_id and again.version == out.version
    assert built.one("SELECT count(*) FROM chat_sessions WHERE node_id = 'extra'") == 1
    assert built.one("SELECT value FROM meta WHERE key = 'graph_version'") == version and built.events.events == []


def test_ensure_node_gives_a_node_without_an_active_session_a_new_one_and_keeps_an_existing_one(built):
    from sutra_app.orchestrator.nodes import ensure_node, node_init
    spec = node_init(_structural("extra", department_id="web", parent_id="web"))
    with built.db.tx() as tx:
        first = ensure_node(tx, spec, graph=built.graph)
    built.sql("UPDATE chat_sessions SET status = 'archived', writable = 0 WHERE id = ?", first.chat_session_id)
    with built.db.tx() as tx:
        second = ensure_node(tx, spec, graph=built.graph, new_session_id=lambda: "cs_00000000beef")
    assert second.chat_session_id == "cs_00000000beef" and built.graph.get("extra").chat_session_id == "cs_00000000beef"
    assert built.one("SELECT count(*) FROM chat_sessions WHERE node_id = 'extra' AND status = 'active'") == 1


def test_ensure_node_rejects_what_the_gate_or_the_session_rules_reject_and_leaves_nothing_behind(built):
    from sutra_app.library.gate import GateError
    from sutra_app.library.node import step_node_id
    from sutra_app.orchestrator.models import NodeInit
    from sutra_app.orchestrator.nodes import ensure_node, node_init
    step = _structural(step_node_id("tsk_000000000001", "task"), "step", department_id="web", task_id="tsk_000000000001", step_ref="task")
    cases = [
        (GateError, node_init(_structural("zed", "division", department_id="nope"))),           # the node names a department that is not there
        (ValueError, NodeInit(node={"label": "x"}, session_title="x")),                          # no id, no kind
        (ValueError, node_init(step).model_copy(update={"writable": True}))]                     # a step's chat is a read-only log
    for error, spec in cases:
        with built.db.tx() as tx:
            with pytest.raises(error):
                ensure_node(tx, spec, graph=built.graph)                                         # caught inside the transaction, which then commits
    assert built.one("SELECT count(*) FROM chat_sessions WHERE node_id = 'zed' OR node_id LIKE 's-%'") == 0
    assert built.one("SELECT count(*) FROM graph_nodes WHERE id = 'zed'") == 0
