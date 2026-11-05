"""GraphStore (ORCH-4): the pre-order view, the wire fields, function meta, NodeDetail, put_node / put_edge, aggregate.

`World` builds a small graph straight into the tables (the chart rows are ChartStore's and the sessions are `ensure_node`'s, both
other packages): root, sales (leads, quotes), web (menu), five function nodes per department, one session per node.
`tests/orchestrator/test_api_graph.py` imports it."""
import json

import pytest
from factories_node import stored_edge, toy_specs

from sutra_app.library.department import Department
from sutra_app.library.gate import GATE
from sutra_app.library.node import StructuralNode, check_graph, new_function_node, step_node_id
from sutra_app.library.types import FUNCTIONS
from sutra_app.orchestrator.errors import NotFound
from sutra_app.orchestrator.graph import ATOMS_SHOWN, RECENT_TERMINAL_TASKS, GraphStore
from sutra_app.orchestrator.models import GraphNodeOut

CHART_TREE = {"sales": {"leads": {}, "quotes": {}}, "web": {"menu": {}}}
SPECS = toy_specs()


def tid(n: int) -> str:
    return f"tsk_{n:012x}"


def sid(n: int) -> str:
    return f"cs_{n:012x}"


class World:
    """root, sales (leads, quotes), web (menu); graph nodes, org rows and sessions all in place."""

    def __init__(self, db, clock) -> None:
        from factories_org import make_chart
        self.db, self.clock = db, clock
        self.store = GraphStore(db, specs=SPECS)
        self.chart = make_chart(CHART_TREE)
        self.sessions = 0
        self.session_of: dict[str, str] = {}
        with db.tx() as tx:
            checked = GATE.check("org_chart", self.chart)
            tx.conn.execute("INSERT INTO org_charts(revision, body, sha256, ts) VALUES (1, ?, ?, 0)", (checked.json, checked.sha256))
            parents = {e.child: e.parent for e in self.chart.edges}
            positions: dict[str, int] = {}
            for node in self.chart.nodes:
                tx.conn.execute("INSERT INTO org_nodes(id, kind, name, created_rev, ts) VALUES (?,?,?,1,0)", (node.id, node.kind, node.name))
                if node.id in parents:
                    position = positions[parents[node.id]] = positions.get(parents[node.id], -1) + 1
                    tx.conn.execute("INSERT INTO org_edges(parent_id, child_id, position) VALUES (?,?,?)", (parents[node.id], node.id, position))
                if node.kind == "department":
                    dep = GATE.check("department", Department(id=node.id, home_dir=f"departments/{node.id}", ts_created=1))
                    tx.conn.execute("INSERT INTO departments(id, home_dir, body, sha256, ts) VALUES (?,?,?,?,1)",
                                    (node.id, f"departments/{node.id}", dep.json, dep.sha256))
                kwargs = dict(id=node.id, kind=node.kind, label=node.name, parent_id=parents.get(node.id),
                              department_id=self.chart.department_of(node.id), chat_session_id=self._session(tx, node.id, node.kind),
                              ts_created=1, ts_updated=1)
                self.store.put_node(tx, GATE.check("node", StructuralNode(**kwargs), ctx=tx.ctx))
                if node.kind == "department":
                    for fn in FUNCTIONS:
                        model = new_function_node(node.id, fn, SPECS, 1)
                        model = model.evolve(chat_session_id=self._session(tx, model.id, "function"))
                        self.store.put_node(tx, GATE.check("node", model, ctx=tx.ctx))
        events = getattr(db, "_publish", None)
        if hasattr(events, "batches"):
            events.batches.clear()

    def _session(self, tx, node_id: str, kind: str) -> str:
        self.sessions += 1
        session_id = "cs_org" if node_id == "root" else sid(self.sessions)
        tx.conn.execute(
            "INSERT INTO chat_sessions(id, node_id, kind, title, writable, created_at, updated_at) VALUES (?,?,?,?,?,0,0)",
            (session_id, node_id, "org" if kind == "root" else kind, node_id, int(kind in ("root", "department")),))
        self.session_of[node_id] = session_id
        return session_id

    # ---- more rows ------------------------------------------------------------------------------------------------

    def sql(self, text: str, *args):
        return self.db.conn().execute(text, args)

    def task(self, n: int, dept: str, status: str = "running", *, created: int | None = None, run: str | None = "auto", scope=None,
             title: str | None = None, with_step: bool = True) -> str:
        task_id = tid(n)
        run_id = f"j2-20261104-1000{n:02d}-aaaa" if run == "auto" else run
        self.sql("INSERT INTO tasks(id, dept_id, scope_node_id, title, user_text, status, run_id, created_at) VALUES (?,?,?,?,?,?,?,?)",
                 task_id, dept, scope, title or f"Task {n}", "u", status, run_id, created if created is not None else n)
        if with_step:
            self.step(task_id, "task", scope or dept, label=title or f"Task {n}", ts=1000 + n)
        return task_id

    def step(self, task_id: str, ref: str, parent: str, *, label: str | None = None, ts: int = 2000, state: str = "idle", dept=None) -> str:
        dept = dept or self.sql("SELECT dept_id FROM tasks WHERE id = ?", task_id).fetchone()[0]
        node_id = step_node_id(task_id, ref)
        with self.db.tx() as tx:
            model = StructuralNode(id=node_id, kind="step", label=label or ref, parent_id=parent, department_id=dept, task_id=task_id,
                                   step_ref=ref, state=state, chat_session_id=self._session(tx, node_id, "step"), ts_created=ts, ts_updated=ts)
            self.store.put_node(tx, GATE.check("node", model, ctx=tx.ctx))
        return node_id

    def atom(self, node_id: str, display: str, *, n: int, schema: str = "work-atom/0.3", task: str | None = None, goal: str | None = None) -> str:
        state = {"verify_failed": "abandoned"}.get(display, display) if schema == "work-atom/0.3" else display
        atom_id = f"a-{n:010x}-01" if schema == "work-atom/0.3" else f"j2-20261104-100001-aaaa:W-{n}.a1"
        self.sql("INSERT INTO atoms(id, schema, node_id, task_id, state, display, attempt, goal, body, sha256, ts_open) VALUES (?,?,?,?,?,?,1,?,?,'x',?)",
                 atom_id, schema, node_id, task, state, display, goal or f"goal {n}", json.dumps({"n": n}), 5000 + n)
        return atom_id

    def usage(self, ref: str, *, provider="claude", node=None, task=None, dept=None, atom=None, usd=None, tin=None, tout=None) -> None:
        self.sql("INSERT INTO usage_ledger(at, provider, purpose, node_id, task_id, dept_id, atom_id, usd, tokens_in, tokens_out, call_ref)"
                 " VALUES (1,?,?,?,?,?,?,?,?,?,?)", provider, "p", node, task, dept, atom, usd, tin, tout, ref)

    def fn_node(self, dept: str, fn: str, **over):
        """Re-store a function node with changes (state, wait_on, stats, ...)."""
        with self.db.tx() as tx:
            model = tx.ctx.get("node", f"{dept}.{fn}").evolve(**over)
            return self.store.put_node(tx, GATE.check("node", model, ctx=tx.ctx))

    def ids(self, **kw) -> list[str]:
        return [n.id for n in self.store.view(**kw).nodes]


@pytest.fixture
def world(db, clock):
    return World(db, clock)


def by_id(view):
    return {n.id: n for n in view.nodes}


FUNCS_OF = lambda dept: [f"{dept}.{fn}" for fn in FUNCTIONS]       # noqa: E731


# ---- the order of the view ---------------------------------------------------------------------------------------------------------

def test_chart_level_is_the_chart_in_pre_order_without_function_nodes(world):
    assert world.ids(level="chart") == ["root", "sales", "leads", "quotes", "web", "menu"]


def test_full_level_puts_the_five_functions_after_the_chart_children_in_the_fixed_order(world):
    assert world.ids(level="full") == [
        "root", "sales", "leads", "quotes", *FUNCS_OF("sales"), "web", "menu", *FUNCS_OF("web")]
    assert FUNCTIONS == ("identity", "adaptation", "priority", "coordination", "audit")


def test_chart_children_follow_org_edges_position_not_the_alphabet(world):
    world.sql("UPDATE org_edges SET position = 5 WHERE child_id = 'leads'")
    world.sql("UPDATE org_edges SET position = 6 WHERE parent_id = 'root' AND child_id = 'sales'")
    world.sql("UPDATE org_edges SET position = 1 WHERE parent_id = 'root' AND child_id = 'web'")
    assert world.ids(level="chart") == ["root", "web", "menu", "sales", "quotes", "leads"]


def test_steps_come_last_by_creation_time_then_id_and_nest_under_their_parent(world):
    t1 = world.task(1, "sales", "done")
    t2 = world.task(2, "sales", "running", scope="quotes")
    s_w1 = world.step(t2, "W-1", step_node_id(t2, "task"), ts=3000)
    s_w2 = world.step(t2, "W-2", step_node_id(t2, "task"), ts=2999)
    ids = world.ids(level="full")
    assert ids.index(step_node_id(t1, "task")) > ids.index(f"sales.audit")                            # after the functions
    quotes = ids.index("quotes")
    assert ids[quotes:quotes + 4] == ["quotes", step_node_id(t2, "task"), s_w2, s_w1]               # a scoped task hangs on its division; W-2 is older
    assert ids.index(step_node_id(t1, "task")) < ids.index("web")                                   # depth first: all of sales before web


def test_creation_time_beats_the_id_when_they_disagree(world):
    t = world.task(1, "web")
    low, high = sorted([step_node_id(t, "W-1"), step_node_id(t, "W-2")])
    refs = {step_node_id(t, "W-1"): "W-1", step_node_id(t, "W-2"): "W-2"}
    world.step(t, refs[high], "web", ts=10)                                  # the larger id is the older step
    world.step(t, refs[low], "web", ts=20)
    ids = world.ids(level="full")
    assert ids.index(high) < ids.index(low)


def test_two_steps_with_one_creation_time_are_ordered_by_id(world):
    t = world.task(1, "web")
    a = world.step(t, "W-1", "web", ts=7)
    b = world.step(t, "W-2", "web", ts=7)
    ids = world.ids(level="full")
    assert ids.index(min(a, b)) < ids.index(max(a, b))


# ---- chart level vs full level: which steps ----------------------------------------------------------------------------------------

def test_chart_level_shows_each_departments_latest_task_step_only(world):
    old = world.task(1, "sales", "done", created=10)
    new = world.task(2, "sales", "running", created=20)
    world.step(new, "W-1", step_node_id(new, "task"))
    web = world.task(3, "web", "queued", created=15)
    ids = world.ids(level="chart")
    assert step_node_id(old, "task") not in ids and step_node_id(new, "task") in ids and step_node_id(web, "task") in ids
    assert not any(i for i in ids if i.endswith(step_node_id(new, "W-1")))                              # no workflow step at chart level


def test_full_level_shows_live_tasks_and_the_newest_finished_ones_per_department(world):
    live = world.task(1, "web", "waiting_user", created=1)
    finished = [world.task(10 + i, "web", "done", created=10 + i) for i in range(RECENT_TERMINAL_TASKS + 2)]
    other = world.task(30, "sales", "crashed", created=5)
    ids = set(world.ids(level="full"))
    assert step_node_id(live, "task") in ids and step_node_id(other, "task") in ids                    # the live one is always there
    shown = [t for t in finished if step_node_id(t, "task") in ids]
    assert shown == finished[-RECENT_TERMINAL_TASKS:]                                                  # the newest five of the finished ones


def test_task_filter_keeps_only_that_tasks_steps(world):
    a = world.task(1, "web", "done")
    b = world.task(2, "web", "running")
    wb = world.step(b, "W-1", step_node_id(b, "task"))
    ids = world.ids(level="full", task=b)
    assert step_node_id(a, "task") not in ids and {step_node_id(b, "task"), wb} <= set(ids)
    assert world.ids(level="chart", task=b).count(wb) == 0                                             # chart level: the task step only
    with pytest.raises(NotFound):
        world.store.view(task=tid(99))


def test_dept_filter_keeps_the_subtree_and_the_way_up(world):
    t = world.task(1, "web")
    assert world.ids(level="full", dept="web") == ["root", "web", "menu", *FUNCS_OF("web"), step_node_id(t, "task")]
    assert world.ids(level="chart", dept="sales") == ["root", "sales", "leads", "quotes"]
    for bad in ("menu", "nope", "web.identity"):
        with pytest.raises(NotFound):
            world.store.view(dept=bad)


def test_an_unknown_level_is_refused(world):
    with pytest.raises(ValueError, match="chart"):
        world.store.view(level="deep")


# ---- the wire fields ---------------------------------------------------------------------------------------------------------------

def test_wire_fields_of_every_node_kind(world):
    t = world.task(1, "web", "running", run="j2-20261104-100001-7f3a")
    nodes = by_id(world.store.view(level="full"))
    root, web, menu, ident = nodes["root"], nodes["web"], nodes["menu"], nodes["web.identity"]
    step = nodes[step_node_id(t, "task")]
    assert (root.kind, root.org_node_id, root.dept_id, root.chat_session_id, root.meta) == ("root", "root", None, "cs_org", {})
    assert (web.kind, web.org_node_id, web.dept_id, web.label, web.status) == ("department", "web", "web", "Web", "idle")
    assert (menu.kind, menu.dept_id, menu.org_node_id) == ("division", "web", "menu")
    assert (ident.kind, ident.fn, ident.org_node_id, ident.dept_id, ident.label, ident.step_ref) == ("function", "identity", None, "web", "Identity", None)
    assert (step.kind, step.task_id, step.step_ref, step.org_node_id, step.dept_id, step.fn) == ("step", t, "task", None, "web", None)
    assert web.meta == {"run_id": "j2-20261104-100001-7f3a"} == step.meta                              # departments and steps carry the run
    assert all(isinstance(n, GraphNodeOut) and n.version >= 1 for n in nodes.values())


def test_run_id_is_left_out_while_a_task_has_no_run_and_a_live_run_wins_for_the_department(world):
    queued = world.task(1, "sales", "queued", run=None)
    nodes = by_id(world.store.view(level="chart"))
    assert nodes["sales"].meta == {} and nodes[step_node_id(queued, "task")].meta == {}
    world.task(2, "web", "done", created=5, run="j2-20261104-100002-aaaa")
    world.task(3, "web", "running", created=2, run="j2-20261104-100003-bbbb")                           # older, but live
    assert by_id(world.store.view())["web"].meta == {"run_id": "j2-20261104-100003-bbbb"}


def test_status_is_the_node_state_and_detail_is_passed_on(world):
    world.fn_node("web", "audit", state="waiting_on_you", wait_on="you", detail="asks about the menu")
    node = by_id(world.store.view(level="full"))["web.audit"]
    assert (node.status, node.detail) == ("waiting_on_you", "asks about the menu")


def test_every_node_has_one_session(world):
    """I1 on the view: the wire's chat_session_id is the node's one active session (the creator is ORCH-5's ensure_node)."""
    for node in world.store.view(level="full").nodes:
        active = [r[0] for r in world.sql("SELECT id FROM chat_sessions WHERE node_id = ? AND status = 'active'", node.id)]
        assert active == [node.chat_session_id] and node.chat_session_id


def test_view_versions_and_the_chart_revision(world):
    view = world.store.view()
    assert view.chart_version == 1 and view.version == _version_bump(world) > 0
    world.sql("INSERT INTO org_charts(revision, body, sha256, ts) VALUES (4, '{}', 'x', 0)")
    assert world.store.view().chart_version == 4                                                      # the newest revision


def _version_bump(world) -> int:
    return int(world.sql("SELECT value FROM meta WHERE key = 'graph_version'").fetchone()[0])


def test_derived_edges_follow_the_walk_and_no_contains_is_stored(world):
    t = world.task(1, "web")
    view = world.store.view(level="full", dept="web")
    kinds = [(e.src, e.dst, e.kind) for e in view.edges]
    assert kinds[0] == ("root", "web", "contains") and ("web", "menu", "contains") in kinds
    assert ("web", "web.identity", "has_function") in kinds and ("web", step_node_id(t, "task"), "has_step") in kinds
    assert world.sql("SELECT count(*) FROM graph_edges").fetchone()[0] == 0                              # I7: nothing derived is stored
    assert len([e for e in kinds if e[2] == "has_function"]) == 5


def test_stored_edges_appear_when_both_ends_are_in_the_view(world):
    t = world.task(1, "web")
    other = world.task(2, "sales")
    w1 = world.step(t, "W-1", step_node_id(t, "task"))
    w2 = world.step(t, "W-2", step_node_id(t, "task"))
    with world.db.tx() as tx:
        for edge in (stored_edge("depends_on", w2, w1, label="reads"), stored_edge("handoff", "web.identity", "web.audit"),
                     stored_edge("speaks_to", "web.priority", "web.coordination", n=4), stored_edge("step", w1, step_node_id(other, "task"))):
            world.store.put_edge(tx, GATE.check("edge", edge, ctx=tx.ctx))
    edges = {(e.src, e.dst, e.kind): e.label for e in world.store.view(level="full", dept="web").edges}
    assert edges[(w2, w1, "depends_on")] == "reads"
    assert edges[("web.identity", "web.audit", "handoff")] == ""
    assert edges[("web.priority", "web.coordination", "speaks_to")] == "4"                              # the message count labels the line
    assert (w1, step_node_id(other, "task"), "step") not in edges                                       # one end is outside the department
    assert (w1, step_node_id(other, "task"), "step") in {(e.src, e.dst, e.kind) for e in world.store.view(level="full").edges}
    assert all(e.kind != "handoff" for e in world.store.view(level="chart").edges)                      # function nodes are not in the overview


# ---- function meta -------------------------------------------------------------------------------------------------------------------

def test_function_meta_in_the_view_is_exactly_stats_and_wait_on(world):
    world.fn_node("web", "identity", stats={"calls": 12, "seconds": 41.5, "tokens": {"input": 7000, "output": 2120}},
                  state="waiting_on_you", wait_on="you")
    meta = by_id(world.store.view(level="full"))["web.identity"].meta
    assert set(meta) == {"stats", "wait_on"} and meta["wait_on"] == "you"
    assert meta["stats"] == {"calls": 12, "seconds": 41.5, "tokens_in": 7000, "tokens_out": 2120,
                             "atoms_open": 0, "atoms_closed": 0, "atoms_failed": 0, "atoms_total": 0}
    assert by_id(world.store.view(level="full"))["web.audit"].meta["wait_on"] is None


def test_atom_counts_equal_the_counts_over_atoms_display(world):
    node = "web.identity"
    for n, display in enumerate(["open", "closed", "closed", "verify_failed", "verify_failed", "verify_failed", "abandoned", "refused"], 1):
        world.atom(node, display, n=n)
    world.atom("sales.identity", "closed", n=40)                                                         # another node's atom is not counted
    stats = by_id(world.store.view(level="full"))[node].meta["stats"]
    assert (stats["atoms_open"], stats["atoms_closed"], stats["atoms_failed"], stats["atoms_total"]) == (1, 2, 3, 8)
    counted = {r[0]: r[1] for r in world.sql("SELECT display, count(*) FROM atoms WHERE node_id = ? GROUP BY display", node)}
    assert stats["atoms_total"] == sum(counted.values()) == counted["open"] + counted["closed"] + counted["verify_failed"] + counted["abandoned"] + counted["refused"]
    assert stats["atoms_failed"] == counted["verify_failed"]


def test_non_function_nodes_have_no_function_meta(world):
    nodes = by_id(world.store.view(level="full"))
    assert nodes["root"].meta == {} and nodes["sales"].meta == {} and nodes["leads"].meta == {}


# ---- NodeDetail --------------------------------------------------------------------------------------------------------------------------

def test_function_node_detail_has_exactly_the_seven_meta_keys(world):
    world.fn_node("web", "audit", state="waiting", wait_on="identity")
    world.atom("web.audit", "closed", n=1)
    world.atom("web.audit", "verify_failed", n=2)
    detail = world.store.node("web.audit")
    meta = detail.node.meta
    assert set(meta) == {"goal", "task", "context", "constraints", "wait_on", "hands_to", "stats"}
    assert meta["goal"] == SPECS.specs["audit"].goal and meta["task"] == SPECS.specs["audit"].role
    assert meta["context"] == SPECS.specs["audit"].reads and meta["constraints"] == SPECS.specs["audit"].may_not
    assert meta["wait_on"] == "identity" and meta["hands_to"] == ["identity"]
    assert meta["stats"]["atoms_failed"] == 1 and meta["stats"]["atoms_total"] == 2                       # atoms_failed and atoms_total are in the drawer


@pytest.mark.parametrize("fn, expected", [
    ("identity", ["adaptation", "priority", "coordination", "audit"]),
    ("adaptation", ["priority", "identity", "audit", "coordination"]),
    ("priority", ["adaptation", "identity", "coordination"]),
    ("coordination", ["priority", "adaptation", "identity", "audit"]),
    ("audit", ["identity"]),
])
def test_hands_to_follows_the_handoff_table(world, fn, expected):
    assert world.store.node(f"sales.{fn}").node.meta["hands_to"] == expected


def test_detail_reads_specs_from_a_loader_once():
    calls = []

    def loader():
        calls.append(1)
        return SPECS

    store = GraphStore(None, specs=loader)          # the database is not touched by specs()
    assert store.specs() is SPECS and store.specs() is SPECS and calls == [1]


def test_detail_of_a_non_function_node_keeps_its_plain_meta(world):
    t = world.task(1, "web", run="j2-20261104-100001-7f3a")
    assert world.store.node("web").node.meta == {"run_id": "j2-20261104-100001-7f3a"}
    assert world.store.node("leads").node.meta == {}
    assert world.store.node(step_node_id(t, "task")).node.kind == "step"


def test_unknown_node_is_not_found(world):
    with pytest.raises(NotFound):
        world.store.node("web.nothing")


def test_detail_session_is_the_active_one_and_archived_chats_are_those_filed_under_it(world):
    world.sql("INSERT INTO chat_sessions(id, node_id, kind, title, status, writable, filed_under, created_at, updated_at)"
              " VALUES (?, 'old', 'division', 'Old', 'archived', 0, 'leads', 5, 5), (?, 'older', 'division', 'Older', 'archived', 0, 'leads', 4, 4)",
              sid(900), sid(901))
    detail = world.store.node("leads")
    assert detail.session.id == world.session_of["leads"] and detail.session.kind == "division" and detail.session.writable is False
    assert [c.id for c in detail.archived_chats] == [sid(901), sid(900)] and all(c.status == "archived" and c.filed_under == "leads" for c in detail.archived_chats)
    assert world.store.node("web").session.writable is True
    assert world.store.node("quotes").archived_chats == []


def test_detail_atoms_list_the_open_one_first_then_the_newest_twenty(world):
    node = "web.priority"
    for n in range(1, 31):
        world.atom(node, "closed", n=n)
    world.atom(node, "open", n=0)                                       # the oldest by number, but it is open
    atoms = world.store.node(node).atoms
    assert len(atoms) == 1 + ATOMS_SHOWN and atoms[0].state == "open"
    assert [a.body["n"] for a in atoms[1:]] == list(range(30, 10, -1))
    assert world.store.node(node).node.meta["stats"]["atoms_total"] == 31      # the total is the meta's, not the list's


def test_detail_atoms_of_both_schemas_carry_the_display_state_and_usage(world):
    t = world.task(1, "web")
    step = step_node_id(t, "task")
    fid = world.atom("web.identity", "verify_failed", n=5, task=t)
    bid = world.atom(step, "closed", n=6, schema="atom/1", task=t)
    world.usage("u1", node="web.identity", task=t, atom=fid, usd=0.25, tin=100, tout=10)
    world.usage("u2", node="web.identity", task=t, atom=fid, usd=0.25, tin=50, tout=5)
    world.usage("u3", provider="stub", node="web.identity", task=t, atom=fid, usd=9.0, tin=9, tout=9)        # stub rows are left out
    world.usage("u4", provider="codex", node=step, task=t, atom=bid, tin=70, tout=7)                           # no usd for Codex
    f_atom = world.store.node("web.identity").atoms[0]
    assert (f_atom.id, f_atom.schema_, f_atom.state, f_atom.goal, f_atom.task_id) == (fid, "work-atom/0.3", "verify_failed", "goal 5", t)
    assert f_atom.usage.model_dump() == {"calls": 2, "usd": 0.5, "tokens_in": 150, "tokens_out": 15}
    b_atom = world.store.node(step).atoms[0]
    assert (b_atom.id, b_atom.schema_, b_atom.state) == (bid, "atom/1", "closed")
    assert b_atom.usage.model_dump() == {"calls": 1, "usd": None, "tokens_in": 70, "tokens_out": 7}
    assert f_atom.ts_open == "1970-01-01T01:23:25Z" and f_atom.ts_closed is None


def test_detail_usage_total_excludes_stub_rows_and_a_department_sums_its_team(world):
    world.usage("a", node="web.identity", dept="web", usd=0.4, tin=10, tout=1)
    world.usage("b", node="web.audit", dept="web", usd=0.1, tin=5, tout=2)
    world.usage("c", provider="stub", node="web.identity", dept="web", usd=5.0, tin=5, tout=5)
    assert world.store.node("web.identity").usage_total.model_dump() == {"calls": 1, "usd": 0.4, "tokens_in": 10, "tokens_out": 1}
    assert world.store.node("web").usage_total.model_dump() == {"calls": 2, "usd": 0.5, "tokens_in": 15, "tokens_out": 3}
    assert world.store.node("web.priority").usage_total.model_dump() == {"calls": 0, "usd": None, "tokens_in": None, "tokens_out": None}


def test_detail_task_is_the_steps_own_or_the_departments_live_one(world):
    done = world.task(1, "web", "done", created=1)
    live = world.task(2, "web", "waiting_user", created=2)
    world.usage("a", task=live, usd=0.3, tin=3, tout=1)
    assert world.store.node(step_node_id(done, "task")).task.id == done
    task = world.store.node("web.identity").task
    assert (task.id, task.status, task.dept_name, task.usage.calls, task.usage.usd) == (live, "waiting_user", "Web", 1, 0.3)
    assert world.store.node("web").task.id == live
    assert world.store.node("leads").task is None and world.store.node("sales.audit").task is None


# ---- put_node ----------------------------------------------------------------------------------------------------------------------------

def _checked(tx, node_id: str, **changes):
    return GATE.check("node", tx.ctx.get("node", node_id).evolve(**changes), ctx=tx.ctx)


def test_put_node_inserts_with_version_one_and_stores_the_checked_body(world):
    with world.db.tx() as tx:
        checked = GATE.check("node", StructuralNode(id="support", kind="division", label="Support", parent_id="web", department_id="web"), ctx=tx.ctx)
        assert world.store.put_node(tx, checked) is True
    row = world.sql("SELECT version, body, sha256, ts FROM graph_nodes WHERE id = 'support'").fetchone()
    assert (row["version"], row["body"], row["sha256"]) == (1, checked.json, checked.sha256) and row["ts"] > 0


def test_put_node_returns_false_when_unchanged_even_if_restamped(world, events):
    before = len(events.batches)
    with world.db.tx() as tx:
        assert world.store.put_node(tx, _checked(tx, "web")) is False
        assert world.store.put_node(tx, _checked(tx, "web", ts_updated=999, version=7)) is False         # only version/ts_updated differ
    assert len(events.batches) == before and world.sql("SELECT version FROM graph_nodes WHERE id = 'web'").fetchone()[0] == 1


def test_put_node_bumps_the_row_version_keeps_creation_time_and_rewrites_the_wire_fields(world):
    created = world.sql("SELECT ts FROM graph_nodes WHERE id = 'web'").fetchone()[0]
    with world.db.tx() as tx:
        assert world.store.put_node(tx, _checked(tx, "web", state="running", detail="busy", ts_updated=50)) is True
    with world.db.tx() as tx:
        assert world.store.put_node(tx, _checked(tx, "web", label="Websites")) is True
    row = world.sql("SELECT version, ts, state, detail, label FROM graph_nodes WHERE id = 'web'").fetchone()
    assert tuple(row) == (3, created, "running", "busy", "Websites")


def test_one_graph_updated_per_transaction_with_every_changed_node(world, events):
    with world.db.tx() as tx:
        world.store.put_node(tx, _checked(tx, "web", state="running"))
        world.store.put_node(tx, _checked(tx, "sales", state="running"))
        world.store.put_node(tx, _checked(tx, "web", detail="twice"))                                     # the same node again: still one entry
    updates = [e for e in events.events if e.type == "graph.updated"]
    assert len(updates) == 1
    data = updates[0].data
    assert [n["id"] for n in data["nodes"]] == ["web", "sales"] and data["edges_added"] == data["edges_removed"] == 0
    assert data["nodes"][0]["detail"] == "twice" and data["nodes"][0]["version"] == 3 and data["nodes"][0]["meta"] == {}
    assert data["version"] == _version_bump(world)


def test_graph_version_counts_transactions_not_nodes(world):
    start = _version_bump(world)
    for state in ("running", "idle"):
        with world.db.tx() as tx:
            world.store.put_node(tx, _checked(tx, "web", state=state))
            world.store.put_node(tx, _checked(tx, "sales", state=state))
    assert _version_bump(world) == start + 2


def test_a_function_node_in_graph_updated_carries_stats_and_wait_on_only(world, events):
    world.fn_node("web", "priority", state="waiting", wait_on="adaptation")
    node = [e for e in events.events if e.type == "graph.updated"][-1].data["nodes"][0]
    assert node["id"] == "web.priority" and set(node["meta"]) == {"stats", "wait_on"} and node["meta"]["wait_on"] == "adaptation"


def test_rollback_drops_the_event_and_the_version(world, events):
    start, batches = _version_bump(world), len(events.batches)
    with pytest.raises(RuntimeError):
        with world.db.tx() as tx:
            world.store.put_node(tx, _checked(tx, "web", state="running"))
            raise RuntimeError("boom")
    assert _version_bump(world) == start and len(events.batches) == batches
    assert world.sql("SELECT state FROM graph_nodes WHERE id = 'web'").fetchone()[0] == "idle"


def test_put_node_takes_only_checked_nodes_of_the_node_family(world):
    with world.db.tx() as tx:
        with pytest.raises(TypeError, match="Checked"):
            world.store.put_node(tx, tx.ctx.get("node", "web"))
        with pytest.raises(TypeError, match="edge"):
            world.store.put_node(tx, GATE.check("edge", stored_edge("depends_on", "web.priority", "web.coordination")))
        with pytest.raises(TypeError, match="Checked"):
            world.store.put_edge(tx, "edge")
        with pytest.raises(TypeError, match="node"):
            world.store.put_edge(tx, _checked(tx, "web"))


def test_a_step_node_must_carry_the_library_step_id(world):
    t = world.task(1, "web", with_step=False)
    with world.db.tx() as tx:
        wrong = GATE.check("node", StructuralNode(id="s-0000000000", kind="step", label="x", parent_id="web", department_id="web", task_id=t, step_ref="task"), ctx=tx.ctx)
        with pytest.raises(ValueError, match="step_node_id"):
            world.store.put_node(tx, wrong)


def test_a_node_that_arrives_without_its_session_keeps_the_stored_one(world):
    with world.db.tx() as tx:
        world.store.put_node(tx, _checked(tx, "web", chat_session_id=None, state="running"))
    row = world.sql("SELECT chat_session_id, body FROM graph_nodes WHERE id = 'web'").fetchone()
    assert row["chat_session_id"] == world.session_of["web"] and json.loads(row["body"])["chat_session_id"] == world.session_of["web"]
    with world.db.tx() as tx:
        world.store.put_node(tx, _checked(tx, "web", chat_session_id="cs_ffffffffffff"))
    assert world.sql("SELECT chat_session_id FROM graph_nodes WHERE id = 'web'").fetchone()[0] == "cs_ffffffffffff"      # a new session is taken


def test_get_returns_the_stored_node(world):
    assert world.store.get("web.audit").id == "web.audit" and world.store.get("nothing") is None


def test_gate_failures_are_not_swallowed(world):
    from sutra_app.library.gate import GateError
    with world.db.tx() as tx:
        with pytest.raises(GateError):
            GATE.check("node", StructuralNode(id="ghost-x", kind="division", label="G", parent_id="web", department_id="nope"), ctx=tx.ctx)


# ---- put_edge, delete_edge, delete_node ---------------------------------------------------------------------------------------------------

def _put_edge(world, edge, tx=None):
    def run(t):
        return world.store.put_edge(t, GATE.check("edge", edge, ctx=t.ctx))
    if tx is not None:
        return run(tx)
    with world.db.tx() as t:
        return run(t)


def test_put_edge_stores_once_and_lists_it_in_both_ends(world, events):
    edge = stored_edge("handoff", "web.identity", "web.audit")
    assert _put_edge(world, edge) is True
    assert _put_edge(world, edge) is False                                                                   # nothing new: no write, no event
    row = world.sql("SELECT kind, from_id, to_id, version, task_id FROM graph_edges").fetchone()
    assert tuple(row) == ("handoff", "web.identity", "web.audit", 1, None)
    for end in ("web.identity", "web.audit"):
        assert world.store.get(end).edge_ids == [edge.id]
    update = [e for e in events.events if e.type == "graph.updated"][-1].data
    assert update["edges_added"] == 1 and {n["id"] for n in update["nodes"]} == {"web.identity", "web.audit"}
    assert len([e for e in events.events if e.type == "graph.updated"]) == 1


def test_a_changed_edge_label_updates_the_row_without_counting_an_added_edge(world, events):
    _put_edge(world, stored_edge("speaks_to", "web.priority", "web.coordination", n=1, label="1"))
    assert _put_edge(world, stored_edge("speaks_to", "web.priority", "web.coordination", n=2, label="2")) is True
    row = world.sql("SELECT version, label FROM graph_edges").fetchone()
    assert tuple(row) == (2, "2") and [e.data["edges_added"] for e in events.events if e.type == "graph.updated"] == [1, 0]


def test_a_derived_edge_kind_is_never_stored(world):
    from sutra_app.library.node import make_edge
    for kind, a, b in (("contains", "root", "web"), ("has_function", "web", "web.identity")):
        with world.db.tx() as tx:
            with pytest.raises(ValueError, match="derived"):
                world.store.put_edge(tx, GATE.check("edge", make_edge(kind, a, b), ctx=tx.ctx))
    assert world.sql("SELECT count(*) FROM graph_edges").fetchone()[0] == 0


def test_an_edge_between_steps_remembers_the_task(world):
    t = world.task(1, "web")
    w1, w2 = world.step(t, "W-1", "web"), world.step(t, "W-2", "web")
    _put_edge(world, stored_edge("depends_on", w2, w1, label="reads"))
    assert world.sql("SELECT task_id FROM graph_edges").fetchone()[0] == t


def test_the_graph_with_stored_edges_passes_check_graph(world):
    """I2 and G5: the stored nodes and edges mirror the chart, and node.edge_ids agree with the stored edges."""
    t = world.task(1, "web")
    w1, w2 = world.step(t, "W-1", step_node_id(t, "task")), world.step(t, "W-2", step_node_id(t, "task"))
    _put_edge(world, stored_edge("depends_on", w2, w1, label="reads"))
    _put_edge(world, stored_edge("handoff", "sales.identity", "sales.adaptation"))
    nodes = [world.store.get(r[0]) for r in world.sql("SELECT id FROM graph_nodes")]
    from sutra_app.library.node import derive_edges, GraphEdge
    stored = [GraphEdge.model_validate_json(r[0]) for r in world.sql("SELECT body FROM graph_edges")]
    assert check_graph(world.chart, nodes, [*derive_edges(world.chart, nodes), *stored]) == []


def test_delete_edge_removes_it_from_both_ends(world, events):
    edge = stored_edge("handoff", "web.identity", "web.audit")
    _put_edge(world, edge)
    with world.db.tx() as tx:
        assert world.store.delete_edge(tx, edge.id) is True
        assert world.store.delete_edge(tx, edge.id) is False
    assert world.sql("SELECT count(*) FROM graph_edges").fetchone()[0] == 0
    assert world.store.get("web.identity").edge_ids == [] and [e.data["edges_removed"] for e in events.events if e.type == "graph.updated"][-1] == 1


def test_delete_node_takes_its_stored_edges_with_it(world, events):
    t = world.task(1, "web")
    w1, w2 = world.step(t, "W-1", "web"), world.step(t, "W-2", "web")
    _put_edge(world, stored_edge("depends_on", w2, w1, label="reads"))
    events.batches.clear()
    with world.db.tx() as tx:
        world.store.put_node(tx, _checked(tx, w2, state="running"))
        assert world.store.delete_node(tx, w2) is True
        assert world.store.delete_node(tx, w2) is False
    assert world.sql("SELECT count(*) FROM graph_nodes WHERE id = ?", w2).fetchone()[0] == 0 and world.sql("SELECT count(*) FROM graph_edges").fetchone()[0] == 0
    assert world.store.get(w1).edge_ids == []
    update = [e for e in events.events if e.type == "graph.updated"]
    assert len(update) == 1 and update[0].data["edges_removed"] == 1 and w2 not in [n["id"] for n in update[0].data["nodes"]]
    assert w2 not in world.ids(level="full")


def test_touch_counts_a_transaction_once(world, events):
    start = _version_bump(world)
    with world.db.tx() as tx:
        assert world.store.touch(tx) == start + 1 and world.store.touch(tx) == start + 1
    assert _version_bump(world) == start + 1 and [e.type for e in events.events] == ["graph.updated"]


# ---- aggregate ------------------------------------------------------------------------------------------------------------------------------

def _states(world, *ids):
    return {i: world.sql("SELECT state FROM graph_nodes WHERE id = ?", i).fetchone()[0] for i in ids}


def _aggregate(world):
    with world.db.tx() as tx:
        world.store.aggregate(tx)


def test_aggregate_with_no_tasks_changes_nothing(world, events):
    _aggregate(world)
    assert events.events == [] and set(_states(world, "root", "sales", "web", "leads").values()) == {"idle"}


def test_a_running_task_makes_its_department_and_the_root_running(world):
    world.task(1, "web", "running")
    _aggregate(world)
    assert _states(world, "root", "web", "sales", "menu") == {"root": "running", "web": "running", "sales": "idle", "menu": "idle"}


def test_a_task_waiting_for_the_owner_or_a_waiting_function_makes_the_department_waiting_on_you(world):
    world.task(1, "web", "waiting_user")
    world.task(2, "sales", "running")
    _aggregate(world)
    assert _states(world, "web", "sales", "root") == {"web": "waiting_on_you", "sales": "running", "root": "waiting_on_you"}       # root: waiting > running
    world.sql("UPDATE tasks SET status = 'running' WHERE id = ?", tid(1))
    world.fn_node("web", "identity", state="waiting_on_you", wait_on="you")
    _aggregate(world)
    assert _states(world, "web")["web"] == "waiting_on_you"                                                                          # a function node asks while the task reads running


def test_a_division_mirrors_its_department_only_while_a_task_scoped_to_it_is_live(world):
    world.task(1, "sales", "running", scope="quotes")
    _aggregate(world)
    assert _states(world, "quotes", "leads", "sales") == {"quotes": "running", "leads": "idle", "sales": "running"}
    world.sql("UPDATE tasks SET status = 'done' WHERE id = ?", tid(1))
    _aggregate(world)
    assert set(_states(world, "quotes", "sales", "root").values()) == {"idle"}


def test_a_crashed_last_task_is_a_fault_until_the_next_task_and_the_detail_says_how_it_ended(world):
    world.task(1, "web", "crashed", created=1, title="Menu page")
    world.task(2, "sales", "done_with_open_items", created=1, title="Quotes")
    _aggregate(world)
    web = world.sql("SELECT state, detail FROM graph_nodes WHERE id = 'web'").fetchone()
    assert tuple(web) == ("fault", "last: Menu page, crashed") and _states(world, "root")["root"] == "idle"                          # the root ignores a fault
    assert tuple(world.sql("SELECT state, detail FROM graph_nodes WHERE id = 'sales'").fetchone()) == ("idle", "last: Quotes, done with open items")
    world.task(3, "web", "queued", created=2)                                                                                       # the next task: no longer a fault
    _aggregate(world)
    assert _states(world, "web")["web"] == "idle"


def test_aggregate_leaves_a_running_departments_detail_alone_and_is_stable(world, events):
    world.fn_node("web", "audit", state="idle")
    with world.db.tx() as tx:
        world.store.put_node(tx, _checked(tx, "web", detail="Identity asks about the menu"))
    world.task(1, "web", "running")
    _aggregate(world)
    assert world.sql("SELECT detail FROM graph_nodes WHERE id = 'web'").fetchone()[0] == "Identity asks about the menu"
    events.batches.clear()
    _aggregate(world)                                                                                                                # nothing moved: no write, no event
    assert events.events == []


def test_aggregate_emits_one_graph_updated_for_all_it_changed(world, events):
    world.task(1, "web", "running")
    world.task(2, "sales", "running")
    events.batches.clear()
    _aggregate(world)
    updates = [e for e in events.events if e.type == "graph.updated"]
    assert len(updates) == 1 and {n["id"] for n in updates[0].data["nodes"]} == {"web", "sales", "root"}
