"""The ONE global org chart: its store, its change log and the apply transaction (orchestrator 3.4, 4.1, 5.4; D42, D67, D68).

    chart = ChartStore(db, graph=graph, chats=chats, data_dir=data_dir)
    chart.bootstrap()                                  # no-op when the root exists: revision 1, chg-0001, root node, cs_org, a greeting
    chart.head()                                       # Checked[OrgChart]: the newest revision
    chart.view() / chart.digest(text)                  # ChartView for the UI / the chart as the chat agent reads it
    chart.check(change)                                # ALL violations: the library's apply_change dry run + reuse_candidate + busy
    chart.classify(change)                             # 'approve' iff a rearrange merges or splits divisions, else 'auto'
    chart.apply(change, actor=..., ctx=...)            # ONE transaction: chart revision, projections, nodes, sessions, change row
    chart.decide(change_id, approve)                   # answer a pending approval; idempotent (a second call raises AlreadyDecided)
    chart.history(after, limit) / chart.pending()      # ChartChangeOut rows (the change log)

`ChartStore.apply` is the only writer of `org_charts`, `org_nodes`, `org_edges`, `departments` and `chart_changes` (D67). Every
decision, even a reuse, is a `chart_changes` row with before/after shas, so the log answers "why is this node here" and the shas of
the applied rows chain (I5). The model never picks an id: new nodes carry `$ref`s and the library gives them ids with `slug_id`,
widened by every id ever stored so an id is never reused; a merged-away node becomes a retired `archived` row (the id-reuse guard).

The change row's `id` is assigned here: `chg-<seq>` of the row. A `ChartChange` that arrives with another id is stored with the
assigned one (the result says which). A change that fails inside the transaction (SQL error, a folder that cannot be made) leaves
nothing behind, is logged as a `failed` row in a second small transaction, and raises `ChangeFailed` (failure F5).
"""
import json
import logging
import os
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sutra_app.library.department import Department
from sutra_app.library.gate import GATE, Checked
from sutra_app.library.node import StructuralNode, new_function_node
from sutra_app.library.org_chart import (
    AddOp, ChartChange, ChartChangeInvalid, ChartChangeResult, MergeOp, MoveOp, OrgChart, RenameOp, SplitOp, apply_change, carry_links,
    resolve_alias, seed_chart, slug_id,
)
from sutra_app.library.types import FUNCTIONS, Violation, violation
from sutra_app.orchestrator.chart_rules import ChartRules, classify as classify_change
from sutra_app.orchestrator.chats import ChatStore
from sutra_app.orchestrator.db import Database, Tx
from sutra_app.orchestrator.departments import DepartmentStore
from sutra_app.orchestrator.errors import AlreadyDecided, AppError, NotFound, rules_error
from sutra_app.orchestrator.graph import GraphStore
from sutra_app.orchestrator.ids import IdFactory, iso_z
from sutra_app.orchestrator.models import ChangeContext, ChangeResult, ChartChangeOut, ChartNodeOut, ChartView
from sutra_app.orchestrator.nodes import ensure_node, node_init
from sutra_app.orchestrator.records import ChatMessage, ChatSession
from sutra_app.orchestrator.textutil import one_line_title

__all__ = ["ChartStore", "ChangeFailed", "StoredChange", "ACTORS", "BOOTSTRAP_SUMMARY", "BOOTSTRAP_REASON", "GREETING", "TITLE_CHARS"]

log = logging.getLogger(__name__)
ACTORS = ("chat_agent", "user", "system")
BOOTSTRAP_SUMMARY = "Started the org chart"
BOOTSTRAP_REASON = "The chart starts with the root"
GREETING = "Hello. Tell me what you need and I will give it to the right team."
TITLE_CHARS = 60
MAX_LIMIT = 500
_COLUMNS = ("seq, id, task_id, task_title, kind, actor, base_revision, result_revision, status, summary, reason, session_id, message_id,"
            " body, result_json, plan_json, ops_json, violations, before_sha, after_sha, ts")
_EMPTY_LISTS = {"added": [], "moved": [], "archived": [], "reused": []}


class ChangeFailed(AppError):
    """The change could not be saved (failure F5): the transaction was undone and a `failed` row was logged. `change_id` names it."""

    def __init__(self, change_id: str | None, reason: str) -> None:
        super().__init__("internal", "I could not save that. Nothing was changed.", {"change_id": change_id, "reason": reason})
        self.change_id = change_id


@dataclass
class StoredChange:
    """One change-log row with what the runner needs to resume it: the checked change, the plan it left, why it was refused."""

    out: ChartChangeOut
    change: Checked | None                  # None for the bootstrap row (its body is the seed chart)
    plan: dict[str, Any] | None
    violations: list[dict[str, Any]]
    session_id: str | None
    message_id: int | None


@dataclass
class _Outcome:
    """What one pass of `_apply_in` decided; `violations` non-empty means nothing was stored and the caller raises 422 `rules`."""

    result: ChangeResult | None = None
    violations: list[Violation] = field(default_factory=list)
    mirrors: list[str] = field(default_factory=list)          # departments whose department.json to (re)write after COMMIT
    created_dirs: list[Path] = field(default_factory=list)    # folders made by this attempt (removed again if it fails)
    change_id: str | None = None


class ChartStore:
    """Synchronous (async callers use `run_blocking`). Reads use this thread's connection; writes are one `db.tx()` each."""

    def __init__(self, db: Database, *, graph: GraphStore, chats: ChatStore, data_dir: str | os.PathLike[str],
                 departments: DepartmentStore | None = None, rules: ChartRules | None = None, ids: IdFactory | None = None) -> None:
        self.db = db
        self.graph = graph
        self.chats = chats
        self.data_dir = Path(data_dir)
        self.departments = departments or DepartmentStore(db, self.data_dir)
        self.rules = rules or ChartRules(db)
        self._ids = ids or IdFactory()

    # =================================================================================================================
    # reads
    # =================================================================================================================

    def head(self) -> Checked:
        """The newest revision of the chart as a Checked[OrgChart]."""
        return self._head_in(self.db.conn())

    @staticmethod
    def _head_in(conn: sqlite3.Connection) -> Checked:
        row = conn.execute("SELECT body FROM org_charts ORDER BY revision DESC LIMIT 1").fetchone()
        if row is None:
            raise RuntimeError("the org chart has no revision yet: call ChartStore.bootstrap() first")
        return GATE.check("org_chart", row["body"])

    def view(self) -> ChartView:
        """The live chart for the UI: nodes in chart order with their parent and their position among siblings."""
        chart: OrgChart = self.head().model
        position: dict[str, int] = {}
        out: list[ChartNodeOut] = []
        for node in chart.nodes:
            parent = chart.parent_of(node.id)
            index = position.get(parent, 0) if parent is not None else 0
            if parent is not None:
                position[parent] = index + 1
            out.append(ChartNodeOut(id=node.id, kind=node.kind, name=node.name, purpose=node.purpose, parent_id=parent, position=index))
        return ChartView(version=chart.revision, nodes=out)

    def digest(self, text: str, *, max_chars: int = 6000) -> str:
        """The chart as the chat agent reads it (see `ChartRules.digest`)."""
        return self.rules.digest(self.db.conn(), self.head().model, text, max_chars=max_chars)

    def classify(self, change: Checked | ChartChange) -> str:
        """'approve' iff the change is a rearrange with a merge or a split; everything else is automatic."""
        return classify_change(change.model if isinstance(change, Checked) else change)

    def next_change_id(self) -> str:
        """The id the next change row will get (`chg-0002` ...). `apply` assigns the real one inside its transaction."""
        return IdFactory.change_id(self._next_seq(self.db.conn()))

    def check(self, change: Checked, chart: OrgChart | None = None) -> list[Violation]:
        """ALL the violations of `change` against `chart` (default: the head): the library's `apply_change` dry run (C1 to C12)
        and, unless the base revision is stale, `reuse_candidate` and `busy`. Empty means it can be applied now."""
        self._need(change, "chart_change")
        conn = self.db.conn()
        found, _ = self._violations(conn, change.model, chart if chart is not None else self._head_in(conn).model)
        return found

    def check_assignments(self, drafts: Sequence[Any], chart: OrgChart | None = None, *, added: Sequence[str] = ()) -> list[Violation]:
        """Stage C's `bad_assignment` violations (see `ChartRules.assignments`); `chart` should be the chart after stage B."""
        conn = self.db.conn()
        return self.rules.assignments(conn, drafts, chart if chart is not None else self._head_in(conn).model, added=added)

    def preview(self, change: Checked) -> ChangeResult:
        """What `apply` would do, without storing anything: status 'applied' (or 'pending_approval' when the owner must say yes),
        the real revision, node ids and `ids_by_ref`. Raises the 422 `rules` error when the change has violations."""
        self._need(change, "chart_change")
        conn = self.db.conn()
        chart = self._head_in(conn).model
        found, result = self._violations(conn, change.model, chart)
        if found or result is None:
            raise rules_error(found)
        status = "pending_approval" if classify_change(change.model) == "approve" else "applied"
        lists = _lists_of(result, change.model)
        return ChangeResult(
            id=change.model.id, status=status, decision=change.model.kind, summary=_summary(change.model, chart),
            revision=result.chart.revision if status == "applied" else None, added=lists["added"], moved=lists["moved"],
            archived=lists["archived"], ids_by_ref=dict(result.ids))

    def pending(self) -> list[ChartChangeOut]:
        rows = self.db.conn().execute(f"SELECT {_COLUMNS} FROM chart_changes WHERE status = 'pending_approval' ORDER BY seq").fetchall()
        return [_out_of(r) for r in rows]

    def history(self, after: int = 0, limit: int = 50) -> list[ChartChangeOut]:
        """The change log, oldest first: rows with `seq` above `after` (a cursor), at most `limit` (1 to 500)."""
        rows = self.db.conn().execute(
            f"SELECT {_COLUMNS} FROM chart_changes WHERE seq > ? ORDER BY seq LIMIT ?", (max(int(after), 0), max(1, min(int(limit), MAX_LIMIT)))).fetchall()
        return [_out_of(r) for r in rows]

    def record(self, change_id: str) -> StoredChange:
        """One change row with the checked change, the plan it kept (for a pending approval) and why it was refused."""
        row = self.db.conn().execute(f"SELECT {_COLUMNS} FROM chart_changes WHERE id = ?", (change_id,)).fetchone()
        if row is None:
            raise NotFound("that change")
        return _stored_of(row)

    # =================================================================================================================
    # bootstrap
    # =================================================================================================================

    def bootstrap(self) -> bool:
        """Make revision 1 when there is no root: `org_charts` #1 (`seed_chart`), `chart_changes` #1 (add, by system), the `root`
        projection, the graph node `root`, the writable session `cs_org` and a fixed greeting from Sutra (no model call).
        Returns True when it made them, False (changing nothing) when the root exists."""
        with self.db.tx() as tx:
            if tx.conn.execute("SELECT 1 FROM org_nodes WHERE kind = 'root'").fetchone() is not None:
                return False
            now = tx.now()
            seed = GATE.check("org_chart", seed_chart(ts=now), ctx=tx.ctx)
            chart: OrgChart = seed.model
            tx.conn.execute("INSERT INTO org_charts(revision, body, sha256, ts) VALUES (?,?,?,?)", (chart.revision, seed.json, seed.sha256, now))
            root = chart.nodes[0]
            tx.conn.execute(
                "INSERT INTO org_nodes(id, kind, name, purpose, state, created_rev, ts) VALUES (?,?,?,?, 'active', ?, ?)",
                (root.id, root.kind, root.name, root.purpose, chart.revision, now))
            seq = self._next_seq(tx.conn)
            change_id = IdFactory.change_id(seq)
            lists = {"added": [root.id], "moved": [], "archived": [], "reused": []}
            tx.conn.execute(
                "INSERT INTO chart_changes(seq, id, task_id, task_title, kind, actor, base_revision, result_revision, status, summary, reason,"
                " session_id, message_id, body, result_json, plan_json, ops_json, violations, before_sha, after_sha, ts)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (seq, change_id, "req-0", "", "add", "system", 0, chart.revision, "applied", BOOTSTRAP_SUMMARY, BOOTSTRAP_REASON,
                 None, None, seed.json, json.dumps(lists), None, "[]", None, "", seed.sha256, now))
            tx.conn.execute("INSERT INTO meta(key, value) VALUES ('bootstrapped_at', ?) ON CONFLICT(key) DO NOTHING", (str(now),))
            ensure_node(tx, node_init(StructuralNode(id=root.id, kind="root", label=root.name, ts_created=now, ts_updated=now), title="Sutra"),
                        graph=self.graph, new_session_id=self._ids.session_id)
            greeting = GATE.check("chat_message", ChatMessage(
                kind="text", session_id="cs_org", role="agent", who="sutra", text=GREETING, src_ref="bootstrap:greeting", at=now), ctx=tx.ctx)
            self.chats.post(tx, "cs_org", greeting)
            self._emit_changed(tx, change_id, "add", "applied", chart.revision, lists, BOOTSTRAP_SUMMARY)
        return True

    # =================================================================================================================
    # apply and decide
    # =================================================================================================================

    def apply(self, change: Checked, *, actor: str, ctx: ChangeContext, plan: dict | None = None, approved: bool = False) -> ChangeResult:
        """Decide `change` against the live chart in ONE transaction and log it. The outcomes:

        applied           the chart has a new revision (a reuse only logs a row), projections and nodes follow
        pending_approval  a rearrange with a merge or split, `approved` false: the row keeps the change and `plan` for `decide`
        stale             the change was planned on an older revision: logged, nothing applied
        422 `rules`       the change has violations (AppError, nothing stored; callers run `check` first)
        ChangeFailed      SQL or folder error: undone, a `failed` row logged (F5)"""
        self._need(change, "chart_change")
        if actor not in ACTORS:
            raise ValueError(f"actor is one of {', '.join(ACTORS)}, not {actor!r}")
        outcome = _Outcome()
        try:
            with self.db.tx() as tx:
                self._apply_in(tx, change, outcome, actor=actor, ctx=ctx, plan=plan, approved=approved, existing=None)
        except (sqlite3.Error, OSError) as exc:
            self._cleanup(outcome.created_dirs)
            failed = self._log_failed(change, actor=actor, ctx=ctx, plan=plan, existing=None, why=exc)
            raise ChangeFailed(failed, f"{type(exc).__name__}: {exc}") from exc
        return self._finish(outcome)

    def decide(self, change_id: str, approve: bool) -> ChangeResult:
        """Answer a pending approval. No: the row becomes `rejected`. Yes: the stored change is checked again against the live
        chart; if it now fails (including a chart that moved on) the row becomes `rejected` with the reasons, else it is applied.
        A change that was decided already raises `AlreadyDecided` carrying the first result, so a double click is harmless."""
        outcome = _Outcome()
        existing: sqlite3.Row | None = None
        try:
            with self.db.tx() as tx:
                existing = tx.conn.execute(f"SELECT {_COLUMNS} FROM chart_changes WHERE id = ?", (change_id,)).fetchone()
                if existing is None:
                    raise NotFound("that change")
                if existing["status"] != "pending_approval":
                    raise AlreadyDecided(_result_of(existing))
                change = GATE.check("chart_change", existing["body"])
                lists = json.loads(existing["result_json"])
                if not approve:
                    return self._reject(tx, existing, [violation("", "declined", "You said no, so nothing was changed.")], lists)
                head = self._head_in(tx.conn)
                found, _ = self._violations(tx.conn, change.model, head.model)
                if found:
                    if any(v.code == "stale_base" for v in found):
                        found = [violation("", "stale_base", "The chart changed since you were asked, so nothing was changed.")]
                    return self._reject(tx, existing, found, lists)
                ctx = ChangeContext(session_id=existing["session_id"] or "cs_org", message_id=existing["message_id"],
                                    request_id=existing["task_id"], request_title=existing["task_title"])
                self._apply_in(tx, change, outcome, actor=existing["actor"], ctx=ctx, plan=None, approved=True, existing=existing)
                self.chats.emit_needs_you(tx)
        except (sqlite3.Error, OSError) as exc:
            self._cleanup(outcome.created_dirs)
            if existing is None:
                raise
            failed = self._log_failed(GATE.check("chart_change", existing["body"]), actor=existing["actor"], ctx=None, plan=None, existing=existing, why=exc)
            raise ChangeFailed(failed, f"{type(exc).__name__}: {exc}") from exc
        return self._finish(outcome)

    def _finish(self, outcome: _Outcome) -> ChangeResult:
        if outcome.violations:
            raise rules_error(outcome.violations)
        for dept_id in dict.fromkeys(outcome.mirrors):
            self.departments.write_mirror(dept_id)
        assert outcome.result is not None
        return outcome.result

    # ---- the transaction -----------------------------------------------------------------------------------------------

    def _apply_in(self, tx: Tx, change: Checked, out: _Outcome, *, actor: str, ctx: ChangeContext, plan: dict | None, approved: bool,
                  existing: sqlite3.Row | None) -> _Outcome:
        conn, now = tx.conn, tx.now()
        head = self._head_in(conn)
        before: OrgChart = head.model
        model: ChartChange = change.model
        seq = existing["seq"] if existing is not None else self._next_seq(conn)
        change_id = existing["id"] if existing is not None else IdFactory.change_id(seq)
        out.change_id = change_id
        stored = change if model.id == change_id else GATE.check("chart_change", model.evolve(id=change_id))
        summary = _summary(model, before)
        title = "" if actor == "system" else (ctx.request_title or one_line_title(model.reason, TITLE_CHARS))
        base = dict(seq=seq, change=stored, actor=actor, ctx=ctx, title=title, summary=summary, before_sha=head.sha256, now=now, existing=existing)

        if model.base_revision != before.revision:                                    # planned on an older chart
            lists = _static_lists(before, model)
            self._write_row(tx, status="stale", result_revision=None, after_sha="", lists=lists, plan=plan, violations=[], **base)
            self._emit_changed(tx, change_id, model.kind, "stale", before.revision, lists, summary)
            out.result = ChangeResult(id=change_id, status="stale", decision=model.kind, summary=summary, revision=None,
                                      added=lists["added"], moved=lists["moved"], archived=lists["archived"])
            return out
        found, result = self._violations(conn, model, before)
        if found or result is None:
            out.violations = found
            return out
        lists = _lists_of(result, model)
        if classify_change(model) == "approve" and not approved:                       # the owner must say yes first
            self._write_row(tx, status="pending_approval", result_revision=None, after_sha="", lists=lists, plan=plan, violations=[], **base)
            self._emit_changed(tx, change_id, model.kind, "pending_approval", before.revision, lists, summary)
            tx.emit("chart.approval", {"change_id": change_id, "summary": summary, "message_id": ctx.message_id})
            out.result = ChangeResult(id=change_id, status="pending_approval", decision=model.kind, summary=summary, revision=None,
                                      added=lists["added"], moved=lists["moved"], archived=lists["archived"], ids_by_ref=dict(result.ids))
            return out

        after_sha = head.sha256
        new_chart = result.chart
        self._emit_changed(tx, change_id, model.kind, "applied", new_chart.revision, lists, summary)
        if new_chart.revision != before.revision:
            checked = GATE.check("org_chart", new_chart, ctx=tx.ctx)
            after_sha = checked.sha256
            conn.execute("INSERT INTO org_charts(revision, body, sha256, ts) VALUES (?,?,?,?)", (new_chart.revision, checked.json, checked.sha256, now))
            self._project(tx, before, result, now)
            self._build_nodes(tx, before, result, out, now)
        self.graph.touch(tx)
        self._write_row(tx, status="applied", result_revision=new_chart.revision, after_sha=after_sha, lists=lists, plan=plan, violations=[], **base)
        out.result = ChangeResult(id=change_id, status="applied", decision=model.kind, summary=summary, revision=new_chart.revision,
                                  added=lists["added"], moved=lists["moved"], archived=lists["archived"], ids_by_ref=dict(result.ids))
        return out

    def _reject(self, tx: Tx, row: sqlite3.Row, found: Sequence[Violation], lists: dict[str, list[str]]) -> ChangeResult:
        """Turn a pending row into `rejected` (the owner said no, or the change no longer fits) and keep the plan lists."""
        now = tx.now()
        tx.conn.execute("UPDATE chart_changes SET status = 'rejected', violations = ?, ts = ? WHERE id = ?",
                        (json.dumps([v.model_dump() for v in found]), now, row["id"]))
        head = self._head_in(tx.conn).model
        self._emit_changed(tx, row["id"], row["kind"], "rejected", head.revision, lists, row["summary"])
        self.chats.emit_needs_you(tx)
        return ChangeResult(id=row["id"], status="rejected", decision=row["kind"], summary=row["summary"], revision=None,
                            added=lists["added"], moved=lists["moved"], archived=lists["archived"])

    # ---- the projections --------------------------------------------------------------------------------------------------

    def _project(self, tx: Tx, before: OrgChart, result: ChartChangeResult, now: int) -> None:
        """Bring `org_nodes` and `org_edges` to the new chart. Retired nodes stay as `archived` rows (history and the id guard)."""
        conn, chart = tx.conn, result.chart
        for node in chart.nodes:
            conn.execute(
                "INSERT INTO org_nodes(id, kind, name, purpose, state, created_rev, ts) VALUES (?,?,?,?, 'active', ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET name = excluded.name, purpose = excluded.purpose, state = 'active', merged_into = NULL, archived_rev = NULL",
                (node.id, node.kind, node.name, node.purpose, node.added_in, now))
        for source in result.aliases:
            final = resolve_alias(result.aliases, source)
            if conn.execute("SELECT 1 FROM org_nodes WHERE id = ?", (source,)).fetchone() is None:     # made and merged away in one change
                conn.execute("INSERT INTO org_nodes(id, kind, name, state, created_rev, ts) VALUES (?, 'division', ?, 'active', ?, ?)",
                             (source, source, chart.revision, now))
            conn.execute("UPDATE org_nodes SET state = 'archived', merged_into = ?, archived_rev = ? WHERE id = ?", (final, chart.revision, source))
            conn.execute("UPDATE org_nodes SET merged_into = ? WHERE state = 'archived' AND merged_into = ?", (final, source))
        conn.execute("DELETE FROM org_edges")
        position: dict[str, int] = {}
        parent = {e.child: e.parent for e in chart.edges}
        for node in chart.nodes:
            owner = parent.get(node.id)
            if owner is not None:
                index = position.get(owner, 0)
                position[owner] = index + 1
                conn.execute("INSERT INTO org_edges(parent_id, child_id, position) VALUES (?,?,?)", (owner, node.id, index))

    def _build_nodes(self, tx: Tx, before: OrgChart, result: ChartChangeResult, out: _Outcome, now: int) -> None:
        """Departments, graph nodes and chat sessions for what the change made; chat links, notes and graph rows for what it moved,
        renamed or merged away."""
        conn, chart = tx.conn, result.chart
        specs = self.graph.specs()
        names = {n.id: n.name for n in chart.nodes}
        old_names = {n.id: n.name for n in before.nodes}
        added = sorted(result.added, key=lambda node_id: _depth_of(chart, node_id))
        for node_id in added:                                      # 1. the department record and its folders come first (FKs, I4)
            node = chart.node(node_id)
            if node.kind != "department":
                continue
            home = f"departments/{node_id}"
            record = GATE.check("department", Department(id=node_id, home_dir=home, ts_created=now), ctx=tx.ctx)
            conn.execute("INSERT INTO departments(id, home_dir, body, sha256, ts) VALUES (?,?,?,?,?)", (node_id, home, record.json, record.sha256, now))
            self._make_dirs(self.data_dir / home, out)
            out.mirrors.append(node_id)
        for node_id in added:                                      # 2. graph nodes with their sessions, parents before children
            node = chart.node(node_id)
            structural = StructuralNode(
                id=node_id, kind=node.kind, label=node.name, parent_id=chart.parent_of(node_id), department_id=chart.department_of(node_id),
                ts_created=now, ts_updated=now)
            ensure_node(tx, node_init(structural), graph=self.graph, new_session_id=self._ids.session_id)
        for function_id in result.new_function_nodes:              # 3. the five function nodes of each new department
            dept_id, fn = function_id.rsplit(".", 1)
            fnode = new_function_node(dept_id, fn, specs, now)
            ensure_node(tx, node_init(fnode, title=f"{names[dept_id]} · {fn.capitalize()}"), graph=self.graph, new_session_id=self._ids.session_id)

        if result.aliases:                                         # 4. chat sessions of merged-away divisions (D70)
            links = {}
            for node_id in [n.id for n in before.nodes] + added:
                sid = _active_session(conn, node_id)
                if sid is not None:
                    links[node_id] = sid
            plan = carry_links(links, result)
            self.chats.apply_links(tx, plan, names)
            took: dict[str, list[str]] = {}
            for source in result.aliases:
                final = resolve_alias(result.aliases, source)
                if source in old_names and final in names:
                    took.setdefault(final, []).append(old_names[source])
            for final, sources in took.items():
                self._append_note(tx, _active_session(conn, final), "Took in " + ", ".join(sources))
            for session_id, target in plan.move.items():           # keep I1: the graph node names its active session
                model = tx.ctx.get("node", target)
                if model is not None:
                    self.graph.put_node(tx, GATE.check("node", model.evolve(chat_session_id=session_id, ts_updated=now), ctx=tx.ctx))

        for node in chart.nodes:                                   # 5. labels, parents and departments of nodes that already existed
            current = tx.ctx.get("node", node.id)
            if current is None:
                continue
            want = {"label": node.name, "parent_id": chart.parent_of(node.id), "department_id": chart.department_of(node.id)}
            if all(getattr(current, key, None) == value for key, value in want.items()):
                continue
            self.graph.put_node(tx, GATE.check("node", current.evolve(**want, ts_updated=now), ctx=tx.ctx))
            if current.label != node.name and node.kind != "root":
                self._retitle(tx, node.id, node.name)
                if node.kind == "department":
                    for fn in FUNCTIONS:
                        self._retitle(tx, f"{node.id}.{fn}", f"{node.name} · {fn.capitalize()}")
        for node_id in result.moved:                               # a note in the moved node's own chat
            old_parent, new_parent = before.parent_of(node_id), chart.parent_of(node_id)
            self._set_note(tx, _active_session(conn, node_id), f"Moved from {old_names.get(old_parent, old_parent)} to {names.get(new_parent, new_parent)}")
        for node in chart.nodes:                                   # the mirror of a renamed department shows its new name or purpose
            was = before.node(node.id)
            if node.kind == "department" and was is not None and (was.name, was.purpose) != (node.name, node.purpose):
                out.mirrors.append(node.id)

        for source in result.aliases:                              # 6. a merged-away division: its steps go to the survivor, its node is deleted
            if source not in old_names:
                continue
            final = resolve_alias(result.aliases, source)
            for step in conn.execute("SELECT id FROM graph_nodes WHERE kind = 'step' AND parent_id = ?", (source,)).fetchall():
                model = tx.ctx.get("node", step["id"])
                self.graph.put_node(tx, GATE.check("node", model.evolve(parent_id=final, ts_updated=now), ctx=tx.ctx))
            self.graph.delete_node(tx, source)

    # ---- small writers -----------------------------------------------------------------------------------------------------

    def _write_row(self, tx: Tx, *, seq: int, change: Checked, actor: str, ctx: ChangeContext | None, title: str, summary: str,
                   before_sha: str, now: int, existing: sqlite3.Row | None, status: str, result_revision: int | None, after_sha: str,
                   lists: dict[str, list[str]], plan: dict | None, violations: Sequence[Violation]) -> None:
        model: ChartChange = change.model
        ops_json = json.dumps([op.model_dump(mode="json") for op in model.ops])
        if existing is not None:
            tx.conn.execute(
                "UPDATE chart_changes SET status = ?, result_revision = ?, after_sha = ?, result_json = ?, ts = ?, violations = NULL WHERE id = ?",
                (status, result_revision, after_sha, json.dumps(lists), now, existing["id"]))
            return
        tx.conn.execute(
            "INSERT INTO chart_changes(seq, id, task_id, task_title, kind, actor, base_revision, result_revision, status, summary, reason,"
            " session_id, message_id, body, result_json, plan_json, ops_json, violations, before_sha, after_sha, ts)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (seq, model.id, model.task_id, title, model.kind, actor, model.base_revision, result_revision, status, summary, model.reason,
             ctx.session_id if ctx is not None else None, ctx.message_id if ctx is not None else None, change.json, json.dumps(lists),
             json.dumps(plan) if plan is not None else None, ops_json, json.dumps([v.model_dump() for v in violations]) if violations else None,
             before_sha, after_sha, now))

    def _log_failed(self, change: Checked, *, actor: str, ctx: ChangeContext | None, plan: dict | None, existing: sqlite3.Row | None,
                    why: BaseException) -> str | None:
        """Failure F5: a second small transaction logs a `failed` row (or marks the pending row failed). Never raises."""
        try:
            with self.db.tx() as tx:
                head = self._head_in(tx.conn)
                reasons = [violation("", "failed", f"{type(why).__name__}: {why}")]
                if existing is not None:
                    tx.conn.execute("UPDATE chart_changes SET status = 'failed', violations = ?, ts = ? WHERE id = ?",
                                    (json.dumps([v.model_dump() for v in reasons]), tx.now(), existing["id"]))
                    self._emit_changed(tx, existing["id"], existing["kind"], "failed", head.model.revision, json.loads(existing["result_json"]), existing["summary"])
                    return existing["id"]
                seq = self._next_seq(tx.conn)
                change_id = IdFactory.change_id(seq)
                stored = change if change.model.id == change_id else GATE.check("chart_change", change.model.evolve(id=change_id))
                title = "" if actor == "system" else ((ctx.request_title if ctx is not None else "") or one_line_title(change.model.reason, TITLE_CHARS))
                summary = _summary(change.model, head.model)
                lists = _static_lists(head.model, change.model)
                self._write_row(tx, seq=seq, change=stored, actor=actor, ctx=ctx, title=title, summary=summary, before_sha=head.sha256, now=tx.now(),
                                existing=None, status="failed", result_revision=None, after_sha="", lists=lists, plan=plan, violations=reasons)
                self._emit_changed(tx, change_id, change.model.kind, "failed", head.model.revision, lists, summary)
                return change_id
        except Exception:                                                 # the log is a courtesy: the original error is what matters
            log.exception("could not log the failed chart change")
            return None

    @staticmethod
    def _emit_changed(tx: Tx, change_id: str, kind: str, status: str, revision: int, lists: dict[str, list[str]], summary: str) -> None:
        tx.emit("chart.changed", {
            "revision": revision, "version": revision, "change_id": change_id, "kind": kind, "status": status, "added": list(lists["added"]),
            "moved": list(lists["moved"]), "merged": list(lists["archived"]), "archived": list(lists["archived"]), "summary": summary})

    def _make_dirs(self, folder: Path, out: _Outcome) -> None:
        """`departments/<id>` (0700) and its `runs/`; the folders this call makes are remembered so a failure can remove them."""
        for path in (folder, folder / "runs"):
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.mkdir(mode=0o700)
                out.created_dirs.append(path)

    @staticmethod
    def _cleanup(created: Sequence[Path]) -> None:
        for path in reversed(created):
            try:
                path.rmdir()
            except OSError:
                pass

    def _retitle(self, tx: Tx, node_id: str, title: str) -> None:
        session_id = _active_session(tx.conn, node_id)
        if session_id is not None:
            self._edit_session(tx, session_id, title=title[:200])

    def _set_note(self, tx: Tx, session_id: str | None, note: str) -> None:
        if session_id is not None:
            self._edit_session(tx, session_id, note=note[:500])

    def _append_note(self, tx: Tx, session_id: str | None, note: str) -> None:
        """Add a "Took in ..." note: a session that already took nodes in keeps the earlier names."""
        if session_id is None:
            return
        old = tx.conn.execute("SELECT note FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()["note"]
        if old.startswith("Took in "):
            note = f"{old}, {note[len('Took in '):]}"
        self._edit_session(tx, session_id, note=note[:500])

    def _edit_session(self, tx: Tx, session_id: str, **changes: Any) -> None:
        row = tx.conn.execute(
            "SELECT id, node_id, kind, title, writable, status, filed_under, connector, model, provider_session_id, last_message_id, note,"
            " created_at, updated_at FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
        record = ChatSession(
            kind=row["kind"], id=row["id"], node_id=row["node_id"], title=row["title"], writable=bool(row["writable"]), status=row["status"],
            filed_under=row["filed_under"], connector=row["connector"], model=row["model"], provider_session_id=row["provider_session_id"],
            last_message_id=row["last_message_id"], note=row["note"], created_at=row["created_at"], updated_at=row["updated_at"])
        s: ChatSession = GATE.check("chat_session", record.evolve(**changes, updated_at=max(row["updated_at"], tx.now())), ctx=tx.ctx).model
        tx.conn.execute("UPDATE chat_sessions SET title = ?, note = ?, updated_at = ? WHERE id = ?", (s.title, s.note, s.updated_at, session_id))

    # ---- helpers ----------------------------------------------------------------------------------------------------------

    @staticmethod
    def _need(checked: Any, family: str) -> None:
        if not isinstance(checked, Checked):
            raise TypeError(f"ChartStore takes a Checked {family} from Gate.check, not {type(checked).__name__}")
        if checked.family != family:
            raise TypeError(f"ChartStore takes a Checked {family}, not a Checked {checked.family}")

    @staticmethod
    def _next_seq(conn: sqlite3.Connection) -> int:
        return int(conn.execute("SELECT COALESCE(MAX(seq), 0) FROM chart_changes").fetchone()[0]) + 1

    def _new_id(self, conn: sqlite3.Connection) -> Callable[[str, str, Any], str]:
        """The id factory handed to `apply_change`: `slug_id` with `taken` widened by every id ever stored and the root."""
        used = {r["id"] for r in conn.execute("SELECT id FROM org_nodes")} | {"root"}

        def make(kind: str, name: str, taken: Any) -> str:
            return slug_id(kind, name, set(taken) | used)

        return make

    def _violations(self, conn: sqlite3.Connection, change: ChartChange, chart: OrgChart) -> tuple[list[Violation], ChartChangeResult | None]:
        """(violations, result): the dry run of the library, then our extras (skipped for a stale base: they would judge the wrong chart)."""
        found: list[Violation] = []
        result: ChartChangeResult | None = None
        try:
            result = apply_change(chart, change, new_id=self._new_id(conn))
        except ChartChangeInvalid as exc:
            found = list(exc.violations)
        if any(v.code == "stale_base" for v in found):
            return found, None
        found = found + self.rules.extras(conn, chart, change)
        return found, result


# ---- module helpers -----------------------------------------------------------------------------------------------------------------

def _depth_of(chart: OrgChart, node_id: str) -> int:
    depth, current = 0, node_id
    while current is not None:
        current = chart.parent_of(current)
        depth += 1
    return depth


def _active_session(conn: sqlite3.Connection, node_id: str) -> str | None:
    row = conn.execute("SELECT id FROM chat_sessions WHERE node_id = ? AND status = 'active'", (node_id,)).fetchone()
    return row["id"] if row is not None else None


def _lists_of(result: ChartChangeResult, change: ChartChange) -> dict[str, list[str]]:
    return {"added": list(result.added), "moved": list(result.moved), "archived": list(result.merged), "reused": list(change.reuses)}


def _static_lists(chart: OrgChart, change: ChartChange) -> dict[str, list[str]]:
    """The plan lists of a change that cannot be dry-run (stale, failed): what its ops name that the chart holds. New nodes have no
    ids yet, so `added` is empty."""
    moved = [op.node for op in change.ops if isinstance(op, MoveOp) and chart.node(op.node) is not None]
    archived = [s for op in change.ops if isinstance(op, MergeOp) for s in op.sources if chart.node(s) is not None]
    return {"added": [], "moved": moved, "archived": archived, "reused": list(change.reuses)}


def _summary(change: ChartChange, chart: OrgChart) -> str:
    """One sentence for the change log, written by code from the ops (never by the model): "Added the Web team", "Merged Leads into Quotes"."""
    refs: dict[str, str] = {}
    for op in change.ops:
        if isinstance(op, AddOp):
            refs[op.node.ref] = op.node.name
        elif isinstance(op, SplitOp):
            refs.update({part.ref: part.name for part in op.parts})

    def name(target: str) -> str:
        if target in refs:
            return refs[target]
        found = chart.node(target)
        return found.name if found is not None else target

    if not change.ops:
        return ("Reused " + _join([name(t) for t in change.reuses]))[:500] if change.reuses else "Reused existing teams"
    parts: list[str] = []
    adds: list[str] = []

    def flush() -> None:
        if adds:
            parts.append("Added " + _join(adds))
            adds.clear()

    for op in change.ops:
        if isinstance(op, AddOp):
            adds.append(f"the {op.node.name} {'team' if op.node.kind == 'department' else 'division'}")
            continue
        flush()
        if isinstance(op, MoveOp):
            parts.append(f"Moved {name(op.node)} under {name(op.to_parent)}")
        elif isinstance(op, RenameOp):
            new = op.name or name(op.node)
            parts.append(f"Renamed {name(op.node)} to {new}" if op.name else f"Changed the purpose of {name(op.node)}")
        elif isinstance(op, MergeOp):
            parts.append(f"Merged {_join([name(s) for s in op.sources])} into {name(op.into)}")
        elif isinstance(op, SplitOp):
            parts.append(f"Split {name(op.node)} into {_join([name(op.node)] + [p.name for p in op.parts])}")
    flush()
    return "; ".join(parts)[:500]


def _join(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _lists_from(row: sqlite3.Row) -> dict[str, list[str]]:
    data = json.loads(row["result_json"] or "{}")
    return {key: list(data.get(key, [])) for key in _EMPTY_LISTS}


def _out_of(row: sqlite3.Row) -> ChartChangeOut:
    lists = _lists_from(row)
    return ChartChangeOut(
        seq=row["seq"], id=row["id"], at=iso_z(row["ts"]), actor=row["actor"], decision=row["kind"], status=row["status"], summary=row["summary"],
        reason=row["reason"], task_id=row["task_id"], task_title=row["task_title"], revision=row["result_revision"], added=lists["added"],
        moved=lists["moved"], archived=lists["archived"], reused=lists["reused"])


def _result_of(row: sqlite3.Row) -> ChangeResult:
    """The outcome a decided row stands for (what the first `apply` or `decide` answered)."""
    lists = _lists_from(row)
    status = row["status"] if row["status"] in ("applied", "pending_approval", "rejected", "stale") else "rejected"
    return ChangeResult(id=row["id"], status=status, decision=row["kind"], summary=row["summary"], revision=row["result_revision"],
                        added=lists["added"], moved=lists["moved"], archived=lists["archived"])


def _stored_of(row: sqlite3.Row) -> StoredChange:
    is_change = row["base_revision"] >= 1            # the bootstrap row (base 0) holds the seed chart, not a change
    return StoredChange(
        out=_out_of(row), change=GATE.check("chart_change", row["body"]) if is_change else None,
        plan=json.loads(row["plan_json"]) if row["plan_json"] else None, violations=json.loads(row["violations"]) if row["violations"] else [],
        session_id=row["session_id"], message_id=row["message_id"])
