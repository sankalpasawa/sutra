"""The light node host: the same files and events as an engine run, one model call, a typed verdict (MAN-11)."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from sutra_app import oslayer
from sutra_app.engine.events import EventUsageSink, EventWriter, run_ended_event, run_started_event
from sutra_app.engine.host import handoff as handoff_file
from sutra_app.engine.host.heartbeat import Heartbeat
from sutra_app.engine.llm import NodeCapReached, NodeMeter
from sutra_app.engine.paths import DataPaths, RunDirError
from sutra_app.engine.spec import TaskSpec

from sutra_app.library.types import overhead_atom_id

from . import reviewer

__all__ = ["main", "run"]

EXIT_OK, EXIT_START, EXIT_STOPPED = 0, 3, 130


def _atomic(path: Path, text: str) -> None:
    import secrets
    temp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(temp, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    oslayer.replace(temp, path)


def run(run_dir: Path, *, mock: bool = False, make_port: Optional[Callable[..., Any]] = None, heartbeat_s: float = 5.0) -> int:
    """One reviewer run in `run_dir`. Returns the exit code. The events say `run.started`, beat while the model works and end with `run.ended`; a stop (SIGTERM) ends it `stopped`."""
    task = TaskSpec.model_validate_json((run_dir / "task.json").read_text(encoding="utf-8"))
    node = task.node
    if node is None or node.runtime != "light" or node.role != "reviewer":
        sys.stderr.write("the light node host runs a reviewer node only\n")
        return EXIT_START
    try:
        paths = DataPaths.from_run_dir(run_dir)                  # the data folder is found from the run folder, as the engine host does (PB-2); never from the environment
    except (RunDirError, ValueError) as exc:
        sys.stderr.write(f"{exc}\n")
        return EXIT_START
    writer = EventWriter(run_dir)
    sink = EventUsageSink(writer, default_atom=overhead_atom_id(task.run_id))      # the reviewer's call is a usage row of the run: the ledger, the project's spend and the independence pick see it
    stopping = threading.Event()

    def on_term(signum, frame):                       # noqa: ARG001
        stopping.set()
    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, OSError):
        pass
    writer.emit(run_started_event(pid=os.getpid(), mock=mock, seed="none"))
    beat = Heartbeat(writer, heartbeat_s)
    beat.start()
    meter = NodeMeter(max_calls=min(node.caps.calls, 5), max_usd=node.caps.usd, wall_s=node.caps.wall_s)
    status, outcome = "done", ""
    try:
        reports = reviewer.read_reports(run_dir, task.upstream)
        if mock or not reports:
            raw = {"verdict": "approve", "summary": "Nothing to check." if not reports else "Mock review.", "needs_work": [], "points": []}
        else:
            raw = _ask(task, reviewer.prompt_of(task.user_text, reports), make_port, mock, meter, stopping, paths, sink)
        if stopping.is_set():
            status, outcome = "stopped", "stopped by you"
        else:
            verdict = reviewer.check_verdict(raw)
            _atomic(run_dir / reviewer.VERDICT_FILE, json.dumps(verdict, indent=2) + "\n")
            outcome = f"Done: the reviewer says {verdict['verdict']}"
    except NodeCapReached as cap:
        status, outcome = "crashed", f"stopped: this step {cap}"
    except (reviewer.VerdictInvalid, ValueError, KeyError) as exc:
        status, outcome = "crashed", f"Crashed: the reviewer's verdict could not be used ({type(exc).__name__})"
    except Exception as exc:                          # noqa: BLE001
        status, outcome = "crashed", f"Crashed: {type(exc).__name__}: {str(exc)[:200]}"
    finally:
        beat.stop()
    if status == "done":
        try:
            handoff_file.write(run_dir, handoff_file.build(run_dir, node.id, "done", outcome))
        except OSError:
            pass
    writer.emit(run_ended_event(status=status, outcome=outcome[:2000], code=None if status != "crashed" else "internal"))
    writer.close()
    return EXIT_STOPPED if status == "stopped" else EXIT_OK


def _ask(task: TaskSpec, prompt: str, make_port: Optional[Callable[..., Any]], mock: bool, meter: NodeMeter, stopping: threading.Event, paths: DataPaths, sink: EventUsageSink) -> dict:
    from sutra_app.engine.port import CallTag, CompletionRequest, PortSpec
    if make_port is None:
        from sutra_app.connectors.engine_port import make_port as real
        make_port = real
    spec = PortSpec(mock=mock, connector=task.connector, run_id=task.run_id, dept_id=task.dept_id, task_id=task.task_id, data_dir=str(paths.data_dir),
                    slots=bool(task.node.slots))                  # the machine-wide limit includes the reviewer (SUTRA_NODES_SLOTS)
    port = make_port(spec, usage_sink=sink)
    try:
        meter.begin()
        tag = CallTag(run_id=task.run_id, dept_id=task.dept_id, task_id=task.task_id, function="audit", purpose="review", node_id=task.node.id, node_role="reviewer")
        result = port.complete(CompletionRequest(system="", user=prompt, tag=tag, json_schema=reviewer.VERDICT_SCHEMA, json_mode=True, max_tokens=1200, effort="low"))
        meter.charge(result.usd)
    finally:
        close = getattr(port, "close", None)
        if close is not None:
            close()
    return json.loads(result.text)


def main(argv=None, *, make_port: Optional[Callable[..., Any]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sutra_app.nodes", description="Run one light node (a reviewer).")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args(argv)
    return run(Path(args.run_dir), mock=args.mock, make_port=make_port)
