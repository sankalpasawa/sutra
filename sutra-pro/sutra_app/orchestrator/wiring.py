"""Wiring: `build_services` makes every store and worker and hands them to one `Services`; `start_services` and `stop_services` are
the lifespan's two halves (orchestrator 5.1, 6.4; work package ORCH-8).

    services = build_services(settings, connector=None, launcher=None, clock=None, ids=None)     # no model call, no process
    await start_services(services)       # migrate, bootstrap, sweep, refresh function nodes, reconcile, start_ready
    await stop_services(services)        # turn runner, bus, connector children, stop ladders, WAL checkpoint, database

Building opens no database connection and starts nothing: the data folders are made (mode 0700) because the database file lives
in them, and the connector router is built (in `auto` mode it asks each installed CLI `--help` once). Everything that touches the
database or a process happens in `start_services`, inside the running loop.

Choices made here (docs/notes/ORCH-8.md):
  * an injected `connector` replaces the router for the chat agent; the `/api/connectors` routes are then served by a stub-only
    router (settings copy with connector `stub`), so a test app never probes a real CLI;
  * with `offline` the router's stub gets the demo reply book (`agent/demo.py`, D97): decide, change and assign are answered from the
    message; `SUTRA_CONNECTOR=stub` without offline and every injected connector keep the plain stub;
  * `SUTRA_ENGINE=fake` gives a `FakeLauncher` with no script (a run starts and ends done);
  * logging is configured by the CLI (`configure_logging`), not by `build_services`: a library call must not change the process's logging.
"""
import asyncio
import logging
import sys
from dataclasses import dataclass, field
from typing import Any

import sutra_app
from sutra_app.config import Settings
from sutra_app.connectors.chat_port import RouterChatPort
from sutra_app.connectors.egress import scrubbed
from sutra_app.orchestrator.agent_sessions import session_of
from sutra_app.connectors.factory import build_router as build_connector_router
from sutra_app.connectors.orchestrator_port import AsyncConnector
from sutra_app.library.gate import GATE
from sutra_app.library.node import refresh_function_nodes as library_refresh_function_nodes
from sutra_app.library.types import FUNCTIONS
from sutra_app.orchestrator import agent as _agent_package  # noqa: F401  (registers the chat_turn family)
from sutra_app.orchestrator import records as _records  # noqa: F401  (registers the four orchestrator families)
from sutra_app.orchestrator.agent.agent import ChatAgent
from sutra_app.orchestrator.agent.demo import demo_book
from sutra_app.orchestrator.agent.runner import TurnRunner
from sutra_app.orchestrator.agent_ask import AgentAsk
from sutra_app.orchestrator.atoms import AtomStore
from sutra_app.orchestrator.chart import ChartStore
from sutra_app.orchestrator.attachments import Attachments
from sutra_app.orchestrator.chat_v2 import ChatChoices, recover_interrupted
from sutra_app.orchestrator.chats import ChatStore, ChatTranscripts
from sutra_app.orchestrator.db import Database, run_blocking
from sutra_app.orchestrator.departments import DepartmentStore
from sutra_app.orchestrator.events import EventBus
from sutra_app.orchestrator.graph import GraphStore
from sutra_app.orchestrator.limits import LIMITS_FILE, Limits
from sutra_app.orchestrator.ids import Clock, IdFactory, SystemClock
from sutra_app.orchestrator.notes import prompt_notes
from sutra_app.orchestrator.projector import Projector
from sutra_app.orchestrator.recurring import Recurring
from sutra_app.orchestrator.redact import Redactor
from sutra_app.orchestrator.runs import ProcessLauncher, ReconcileReport, RunWatcher, reconcile
from sutra_app.orchestrator.services import Services
from sutra_app.orchestrator.tasks import TaskGraph, TaskService, TaskStore
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.usage import UsageStore

__all__ = [
    "AppServices", "build_services", "start_services", "stop_services", "make_redactor", "make_launcher", "refresh_function_nodes",
    "configure_logging", "RedactingFormatter", "LOG_FORMAT",
]

log = logging.getLogger(__name__)
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


@dataclass
class AppServices(Services):
    """`Services` plus what only the app shell needs: the connector router (for `/api/connectors`) and the startup report."""

    connector_router: Any = None
    chat_port: Any = None              # ChatPort over the router (ABS-1), for the direct chat routes
    attachments: Any = None            # the attachment service (ABS-4)
    recurring: Any = None              # the schedules of recurring work and their ticker (GAP2 routines-limits)
    limits: Any = None                 # the monthly spending limit and the plan-window guard, TaskService's start gate (GAP2 routines-limits)
    agent_chat: Any = None             # `AgentAsk.turn`: a function's question as a turn of its own chat session, for POST /api/ask (J2 sync 4, D147); the engine's routes read it optionally
    send_setting: Any = None           # what the engine's POST /api/settings calls: a setting as an inbox line to the team's live run (J2 sync 4)
    reconciled: ReconcileReport | None = None
    swept: int = 0
    refreshed: int = 0
    interrupted: int = 0               # owner lines of the org chat the last run accepted and never answered (closed as errors at start)
    started: bool = False
    stopped: bool = False
    problems: list[str] = field(default_factory=list)


# ---- small makers ---------------------------------------------------------------------------------------------------------------

def make_redactor(settings: Settings) -> Redactor:
    """Secrets are the `*KEY/TOKEN/SECRET/PASSWORD/AUTH*` environment values, the `.env` file's values, the launch token and the
    override key (these two at any length)."""
    extra: list[Any] = [settings.token]
    if settings.override_key is not None:
        extra.append(settings.override_key.get_secret_value())
    return Redactor(settings.env_file, extra=extra)


def make_launcher(settings: Settings) -> Any:
    """`SUTRA_ENGINE=process` starts the real engine; `fake` plays no script (a run starts and ends done)."""
    return FakeLauncher() if settings.engine == "fake" else ProcessLauncher()


class RedactingFormatter(logging.Formatter):
    """A formatter that removes every secret from the finished line, traceback included."""

    def __init__(self, redactor: Redactor, fmt: str = LOG_FORMAT) -> None:
        super().__init__(fmt)
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        return self._redactor(super().format(record))


def configure_logging(settings: Settings, redactor: Redactor, *, level: int = logging.INFO, stream: Any = None) -> logging.Handler:
    """Log to `<data>/logs/server.log` and to `stream` (stderr), every line through the redactor. Replaces the handlers a
    previous call installed, so calling it twice leaves one pair. Returns the file handler."""
    settings.ensure_dirs()
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, "_sutra_app", False)]:
        root.removeHandler(handler)
        handler.close()
    formatter = RedactingFormatter(redactor)
    file_handler = logging.FileHandler(settings.log_path, encoding="utf-8")
    console = logging.StreamHandler(stream if stream is not None else sys.stderr)
    for handler in (file_handler, console):
        handler.setFormatter(formatter)
        handler._sutra_app = True                       # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(level)
    try:
        settings.log_path.chmod(0o600)
    except OSError:
        pass
    return file_handler


# ---- build ----------------------------------------------------------------------------------------------------------------------

def build_services(settings: Settings, *, connector: Any = None, launcher: Any = None, clock: Clock | None = None,
                   ids: IdFactory | None = None) -> AppServices:
    """Every store, the bus, the connector layer, the launcher, the watcher, the task service and the turn runner, wired as
    orchestrator 3.4 and 3.5 say. Opens no connection and starts no worker."""
    clock = clock or SystemClock()
    ids = ids or IdFactory(clock)
    redactor = make_redactor(settings)
    settings.ensure_dirs()
    bus = EventBus(clock=clock)
    db = Database(settings.db_path, bus.publish, clock=clock)
    graph = GraphStore(db)
    chats = ChatStore(db)
    departments = DepartmentStore(db, settings.data_dir)
    chart = ChartStore(db, graph=graph, chats=chats, data_dir=settings.data_dir, departments=departments, ids=ids)
    atoms = AtomStore(db, chats=chats, graph=graph, scrub=lambda text: scrubbed(text, redactor))      # a turn's words and reply are the model's text (D157)
    usage = UsageStore(db, chats=chats)
    store = TaskStore(db, settings.data_dir)
    taskgraph = TaskGraph(store, graph, ids=ids)
    projector = Projector(db, graph=graph, chats=chats, atoms=atoms, usage=usage, store=store, taskgraph=taskgraph, clock=clock)
    launcher = launcher if launcher is not None else make_launcher(settings)
    watcher = RunWatcher(projector, store, launcher, interval=settings.watch_ms / 1000, clock=clock, redact=redactor)
    tasks = TaskService(db, store=store, graph=graph, chats=chats, taskgraph=taskgraph, projector=projector, launcher=launcher,
                        settings=settings, watcher=watcher, clock=clock, ids=ids, redact=redactor)
    watcher.after_drain = tasks.start_ready
    watcher.publish = lambda type_, data: bus.publish_one(type_, data)                                   # an agent's live work reaches its chat (D133)
    watcher.agent_session = lambda row, agent: session_of(db.conn(), row, agent)
    # the connector layer: the real router reports usage to the ledger, health and mode to the bus, and session ids to the chats
    router_settings = settings if connector is None else settings.model_copy(update={"connector": "stub"})
    # offline (and only offline) the stub answers the chat agent from the message, so a team can be made with no CLI (D97, GAP-DEMO)
    router = build_connector_router(router_settings, usage_sink=usage, events=lambda type_, data: bus.publish_one(type_, data),
                                    transcripts=ChatTranscripts(chats), session_hook=chats.set_provider,
                                    replybook=demo_book() if router_settings.offline else None, redactor=redactor)
    port = connector if connector is not None else AsyncConnector(router)
    router.choice_source = ChatChoices(db).get                       # the pill governs the org chat agent too (ABS-8)
    attachments = Attachments(settings.data_dir)
    chat_port = RouterChatPort(router, attachments=attachments.store)
    recurring = Recurring(db, tasks, clock=clock, redact=redactor)
    limits = Limits(settings.data_dir / LIMITS_FILE, db, quotas=lambda: {name: router.health.quota(name) for name in ("claude", "codex")},
                    clock=clock, offline=settings.offline or router_settings.connector == "stub")
    tasks.start_gate = limits.gate
    agent_chat = AgentAsk(db=db, tasks=tasks, chats=chats, router=router, chat_port=chat_port, limits=limits, redact=redactor, clock=clock).turn
    agent = ChatAgent(port, chart, redact=redactor, clock=clock, attempts=settings.chat_attempts, timeout=settings.chat_timeout,
                      notes=prompt_notes(db, redactor, clock))                 # the owner's notes, in the decide and assign prompts (GAP2 rules-notes)
    runner = TurnRunner(db=db, chart=chart, chats=chats, tasks=tasks, agent=agent, connector=port,
                        publish=lambda type_, data: bus.publish_one(type_, data), redact=redactor)
    return AppServices(
        settings=settings, version=sutra_app.__version__, db=db, redact=redactor, clock=clock, ids=ids,
        bus=bus, chats=chats, atoms=atoms, usage=usage, graph=graph, chart=chart, departments=departments, tasks=tasks,
        projector=projector, watcher=watcher, runner=runner, connector=port, launcher=launcher,
        resolve_run=tasks.resolve_run, department=departments.row, deliver_to_department=tasks.deliver_to_department,
        stop_live=tasks.stop_live, connector_router=router, chat_port=chat_port, attachments=attachments, recurring=recurring,
        limits=limits, agent_chat=agent_chat, send_setting=tasks.send_setting)


# ---- startup steps --------------------------------------------------------------------------------------------------------------

def refresh_function_nodes(services: Services) -> int:
    """Function nodes stored under an older `FunctionSpec.version` get the spec's goal, task, context and version (nothing else
    changes); they go through the gate. Returns how many were updated."""
    graph = services.graph
    marks = ",".join("?" * len(FUNCTIONS))                  # a function node's kind is its function's name
    ids = [row[0] for row in services.db.conn().execute(f"SELECT id FROM graph_nodes WHERE kind IN ({marks}) ORDER BY id", FUNCTIONS)]
    nodes = [node for node in (graph.get(i) for i in ids) if node is not None]
    stale = library_refresh_function_nodes(graph.specs(), nodes)
    if not stale:
        return 0
    with services.db.tx() as tx:
        changed = 0
        for node in stale:
            if graph.put_node(tx, GATE.check("node", node, ctx=tx.ctx)):
                changed += 1
    return changed


async def start_services(services: AppServices) -> AppServices:
    """Orchestrator 5.1 steps 2, 3, 5, 6 and 7, in this order: migrate; sync an existing template library with the seed (D144: adds what a
    newer seed has, once per seed, never overwrites, never stops the start); bootstrap the chart when there is no root; sweep empty
    department folders and refresh stale function nodes; reconcile the tasks a previous run left (ends with `server.resync`
    restart) and close the org-chat requests it accepted and never answered (`TurnRunner.recover`); the scheduler's catch-up tick and loop
    (recurring.py: one run for the time the app was away); start queued work.
    Idempotent: a second start finds the root, nothing to sweep, nothing stale."""
    if services.started:
        return services
    from sutra_app.ops.doctor import sync_seed_once         # the ops package is not imported by `import sutra_app` (D144)
    await run_blocking(services.db.migrate)
    await run_blocking(sync_seed_once, services.settings.data_dir)          # an existing template library gains what a newer seed has, once per seed; never raises
    await run_blocking(services.chart.bootstrap)
    services.tasks.bind_loop(asyncio.get_running_loop())
    services.swept = await run_blocking(services.departments.sweep)
    services.refreshed = await run_blocking(refresh_function_nodes, services)
    services.reconciled = await reconcile(
        tasks=services.tasks.store, projector=services.projector, watcher=services.watcher, launcher=services.launcher,
        publish=services.bus.publish_one, clock=services.clock)
    await run_blocking(services.tasks.reconcile_choices)          # the agents' picks of every live run are rebuilt from the database (D131)
    marked = await run_blocking(recover_interrupted, services.db, services.chats)     # a direct turn the last process did not finish gets its error line
    if marked:
        log.info("%d direct chat turn(s) of the last run were interrupted and are marked", marked)
    services.interrupted = await run_blocking(services.runner.recover)         # an owner line the last run accepted and never answered becomes an error with Retry
    if services.recurring is not None:                      # the one catch-up for the time the app was away, before the first start_ready
        await services.recurring.start()
    await services.tasks.start_ready()
    services.started = True
    services.stopped = False
    log.info("sutra started: %d department folder(s) swept, %d function node(s) refreshed, %d task(s) reconciled, %d request(s) left open by the last run",
             services.swept, services.refreshed, len(services.reconciled.all()), services.interrupted)
    return services


async def _quietly(what: str, step: Any, services: AppServices) -> None:
    """One shutdown step; a failure is logged and the next step still runs (one broken part must not keep the others open)."""
    try:
        found = step()
        if asyncio.iscoroutine(found):
            await found
    except Exception:                                    # noqa: BLE001
        log.exception("shutdown step failed: %s", what)
        services.problems.append(what)


async def stop_services(services: AppServices) -> None:
    """Orchestrator 5.1 shutdown: the turn runner stops (no new task is made), the bus closes (open event streams end, or the web
    server would wait for them), the connector layer stops its model children, the stop ladders of ALL live tasks run in parallel
    (waiting teams included), their files are drained, a task without `run.ended` becomes stopped ('the app was closed'), the
    watchers end and the WAL is checkpointed; then the database closes. Safe to call twice."""
    if services.stopped:
        return
    services.stopped = True
    services.started = False
    if services.recurring is not None:                      # first: no schedule may make a task while the rest closes
        await _quietly("scheduler", services.recurring.stop, services)
    await _quietly("turn runner", services.runner.close, services)
    await _quietly("event bus", services.bus.close, services)
    router = services.connector_router
    if router is not None:
        await _quietly("connector layer", lambda: run_blocking(router.close), services)
    # the watchers end first: left running, one could see a process the ladder just killed, find no `run.ended` and call the
    # task crashed before `shutdown` has settled it as stopped ('the app was closed': the app caused it, nothing crashed)
    await _quietly("watchers", services.watcher.close, services)
    await _quietly("tasks", services.tasks.shutdown, services)
    await _quietly("database", services.db.close, services)
