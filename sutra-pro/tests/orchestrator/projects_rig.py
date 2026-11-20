"""A rig for the project tests (MAN-5 to MAN-7): the real `TaskService` and `Projector` of `TEnv`, a real `ProjectService`, `NodeControl` and `KillSwitch`, wired as `wiring.build_services`
wires them while SUTRA_NODES_V1 is on, and a way to make a request's tasks the way the chat agent's runner does (reserve, create, link)."""
import json

from orchestrator.test_chart_store import dept_op
from orchestrator.test_tasks import tenv_with

from sutra_app.orchestrator.killswitch import KillSwitch, NodeControl
from sutra_app.orchestrator.nodes_store import NodeStore
from sutra_app.orchestrator.projects import ProjectService, ProjectStep
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher, ev

MORE_TEAMS = ("ops", "hr", "dev", "legal", "finance")


class PRig:
    def __init__(self, db, settings, clock, events, *, owner="edit", launcher=None, teams=True, **settings_changes):
        from sutra_app.orchestrator.limits import LIMITS_FILE, Limits
        self.t = tenv_with(db, settings, clock, events, nodes_v1=True, launcher=launcher or FakeLauncher({"*": [{"hold": True}]}), **settings_changes)
        t = self.t
        if teams:
            for name in MORE_TEAMS:
                t.env.apply(dept_op(f"${name}", name.title()))
        self.owner = owner
        self.switch = KillSwitch(t.settings.data_dir / "nodes", clock=t.clock)
        self.store = NodeStore(t.db, ids=t.ids)
        self.control = NodeControl(self.switch, tasks=t.service, db=t.db, store=self.store, clock=t.clock, kick=t.service.start_ready)
        self.limits = Limits(t.settings.data_dir / LIMITS_FILE, t.db, quotas=lambda: {}, clock=t.clock)           # the real limits file and the real ledger, as wiring has them (D381)
        self.projects = ProjectService(t.db, store=self.store, ids=t.ids, clock=t.clock, settings=t.settings, owner_access=lambda: self.owner, node_control=self.control, tasks=t.service, chats=t.chats,
                                       monthly_limit=self.limits.monthly_limit)
        self.control.projects = self.projects
        t.service.task_gate = self.projects.gate
        t.service.spawn_guard = self.control.spawn_guard
        t.service.node_sync = t.projector.node_sync = self.projects.sync_task
        t.service.node_usd_left = self.projects.usd_left
        t.projector.before_drain = self.projects.prepare_handoff

    # ---- making a request the way the runner does ---------------------------------------------------------------------------------

    def request(self, steps, *, request_id="req-1", budget=None, title="A project", needs=None, scope=None, estimates=None, decide_for_me=False, probe=False):
        """`steps`: (ref, team, [refs it waits for]). Reserves the project, then makes every task and links it in the same transaction. Returns (reservation, {ref: task id})."""
        t = self.t
        project_steps = [ProjectStep(ref=ref, dept_id=dept, depends_on=tuple(deps), needs=tuple((needs or {}).get(ref, ())), scope=tuple((scope or {}).get(ref, ())),
                                     estimate_credits=int((estimates or {}).get(ref, 0))) for ref, dept, deps in steps]
        reservation = self.projects.reserve(request_id, title, project_steps, budget=budget, decide_for_me=decide_for_me)
        tasks = {}
        if reservation is None or not reservation.ok:
            return reservation, tasks
        if probe:                                                              # what the computer has allowed, before any task exists (MAN-15), as the runner does it
            t.run(self.projects.probe_system(reservation.project_id))
        for ref, dept, deps in steps:
            with t.db.tx() as tx:
                task = t.service.create(tx, dept_id=dept, text=f"{ref} of {request_id}", title=ref, depends_on=[tasks[d] for d in deps], request=request_id)
                self.projects.link_task(tx, reservation, ref, task.id)
            tasks[ref] = task.id
        return reservation, tasks

    # ---- helpers ----------------------------------------------------------------------------------------------------------------

    def start(self):
        return self.t.run(self.t.service.start_ready())

    def go(self, task_id):
        """The fake process of a started task says it runs."""
        t = self.t
        t.write_events(task_id, ev("run.started", pid=t.row(task_id).pid, schema="events/1", mock=True, seed="none"))
        t.drain(task_id)

    def finish(self, task_id, status="done", outcome="Done", *, handoff=True, files=None, override=None):
        """The run ends. A node's run that ended well leaves its hand-off first (the host's `handoff` step); `handoff=False` leaves none, `files` puts files in the run folder, `override`
        replaces fields of the hand-off (to make a bad one)."""
        from sutra_app.engine.host import handoff as handoff_file
        t = self.t
        run_dir = t.run_dir(task_id)
        for name, body in (files or {}).items():
            (run_dir / name).write_bytes(body if isinstance(body, bytes) else body.encode())
        node = self.node_of(task_id)
        if handoff and status in ("done", "done_with_open_items") and node is not None:
            document = handoff_file.build(run_dir, node["id"], status, outcome)
            document.update(override or {})
            handoff_file.write(run_dir, document)
        t.write_events(task_id, ev("run.ended", status=status, outcome=outcome))
        t.drain(task_id)

    def sql(self, text, *args):
        return self.t.db.conn().execute(text, args)

    def node_of(self, task_id):
        return self.sql("SELECT * FROM agent_nodes WHERE task_id = ?", task_id).fetchone()

    def node_states(self, tasks):
        return {ref: self.node_of(task_id)["state"] for ref, task_id in tasks.items()}

    def project(self, project_id):
        return self.sql("SELECT * FROM projects WHERE id = ?", project_id).fetchone()

    def audit(self, action=None):
        return [r for r in self.store.audit_rows(limit=500) if action is None or r["action"] == action]

    def detail(self, task_id):
        return self.t.one("SELECT detail FROM graph_nodes WHERE task_id = ? AND step_ref = 'task'", task_id)
