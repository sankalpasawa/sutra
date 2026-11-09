"""The engine process: `main()` (engine design 4.7, flows F1, F5, F7).

    python -m sutra_app.engine --run-dir <data>/departments/<dept>/runs/<run id> [--mock]

One run is one process. The orchestrator makes the run folder, writes `task.json` and the empty `inbox.jsonl` and
`events.jsonl`, and spawns this; the host

 1. checks the folder and reads `task.json` (a bad folder or task: `run.ended{crashed, start_failed}` and exit 2);
 2. resolves the settings, writes `settings.json`, exports the J2 environment BEFORE `engine.j2` is imported (J2 reads it at
    import), seeds the global template library once;
 3. builds the model port (`ScriptedPort` in mock mode, else the connector layer's `make_port` + `preflight`; a failure is
    `run.ended{crashed, start_failed}` and exit 3), binds the call tag and the run overhead atom key (`llm`);
 4. picks the hooks (`SUTRA_HOOKS`, default the function-node layer, falling back to `EventHooks`), imports J2 and makes the
    `J2Run`; decides the seed (`rehydrate`, else fresh with the old files as `upstream`), emits `run.started`, posts the host's
    own `system` lines, starts the publisher, the heartbeat and the inbox, and hands `user_text` to `run.user_says`;
 5. ticks every 150 ms: inbox lines in, publisher notes, thread watch; the run ends when it is `waiting` and not paused:
    final publish, `run.ended`, exit 0.

Exit codes: 0 normal (also a stop line), 2 bad run folder or task, 3 could not start, 70 internal error, 143 SIGTERM.
`main()` returns the code; `python -m sutra_app.engine` passes it to `sys.exit`. `make_port` is the one test seam:
`make_port(sink=..., mock=..., task=..., paths=...)` replaces the default port.
"""
import argparse
import importlib
import json
import os
from sutra_app import oslayer
import re
import shutil
import signal
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from pydantic import ValidationError

from sutra_app.library.types import clip, overhead_atom_id

from .. import llm
from ..events import EventError, EventUsageSink, EventWriter, run_ended_event, run_started_event
from ..hooks import EventHooks, load_validator
from ..paths import DataPaths, RunDirError, load_env_file
from ..port import CallTag, ModelError, PortSpec
from ..rehydrate import HOST_FILES
from ..spec import OUTPUT_NAMES, EngineSettings, SettingsError, TaskSpec, read_settings_file
from .heartbeat import Heartbeat, heartbeat_interval
from .inbox import Inbox

__all__ = ["main", "Host", "StartFailed", "TICK_S", "STOP_WAIT_S", "DEAD_THREAD_GRACE_S", "DEFAULT_HOOKS", "outcome_status",
           "EXIT_OK", "EXIT_BAD_TASK", "EXIT_START_FAILED", "EXIT_INTERNAL", "EXIT_TERM"]

EXIT_OK, EXIT_BAD_TASK, EXIT_START_FAILED, EXIT_INTERNAL, EXIT_TERM = 0, 2, 3, 70, 143
TICK_S = 0.15                      # the inbox is polled every 150 ms
STOP_WAIT_S = 4.0                  # how long a stop waits for the run thread (the whole stop finishes inside 6 s)
DEAD_THREAD_GRACE_S = 1.0          # status "running" with nobody holding the run lock for this long: the run thread died
DEFAULT_HOOKS = "sutra_app.engine.fnodes.layer:factory"
STOP_OUTCOME = "Stopped: stopped on request"
TERM_OUTCOME = "Stopped: the process was asked to stop (SIGTERM)"
UPSTREAM_MAX_BYTES = 20_000_000
SEED_FILES = ("goal.json", "summary.json", "workflows.json", "documents.json")
SEED_TREES = ("site", "artifacts")
SEED_SUFFIXES = (".md", ".docx")
_HOOK_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*")


class StartFailed(Exception):
    """The run cannot start. `reason` is plain words for 'could not start: <reason>'; `exit_code` is 2 or 3."""

    def __init__(self, reason: str, exit_code: int = EXIT_START_FAILED, chat: bool = False):
        super().__init__(reason)
        self.reason, self.exit_code, self.chat = reason, exit_code, chat


def outcome_status(outcome: Optional[str]) -> str:
    """The `run.ended` status of a run that is over, by the rule of J2's `_write_summary`."""
    text = outcome or ""
    for prefix, status in (("Done with open items", "done_with_open_items"), ("Done", "done"), ("Crashed", "crashed")):
        if text.startswith(prefix):
            return status
    return "stopped"


def _parse(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m sutra_app.engine", description="Run one department task (one process).")
    parser.add_argument("--run-dir", required=True, help="<data>/departments/<dept>/runs/<run id>, made by the orchestrator")
    parser.add_argument("--mock", action="store_true", help="scripted replies instead of a model (J2's mock mode)")
    return parser.parse_args(argv)


def main(argv=None, *, make_port: Optional[Callable[..., Any]] = None) -> int:
    args = _parse(argv)
    return Host(args, make_port).execute()


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | oslayer.O_BINARY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    oslayer.replace(tmp, path)


def _stderr(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


class Host:
    """The state of one engine process. `execute()` runs it and returns the exit code."""

    def __init__(self, args, make_port: Optional[Callable[..., Any]] = None):
        self.args = args
        self.make_port = make_port
        self.paths: Optional[DataPaths] = None
        self.writer: Optional[EventWriter] = None
        self.task: Optional[TaskSpec] = None
        self.settings: Optional[EngineSettings] = None
        self.mock = False
        self.port = None
        self.sink: Optional[EventUsageSink] = None
        self.hooks = None
        self.publisher = None
        self.heartbeat: Optional[Heartbeat] = None
        self.inbox: Optional[Inbox] = None
        self.run = None
        self.selection = None                       # the output the engine chose for the brief (capabilities.Selection)
        self.has_folder = False
        self.context = None                         # the capabilities' view of the run (EngineContext), made with the run
        self.stopping = threading.Event()          # set before the port is closed (a stop line or SIGTERM)
        self._terminate = threading.Event()
        self._ended = False
        self._thread_exc: Optional[BaseException] = None
        self._dead_since: Optional[float] = None
        self._saved_hook = None
        self._saved_sigterm = None
        self._function_nodes_off: Optional[str] = None     # why the function-node layer could not be built, else None

    # ---- the whole process --------------------------------------------------------------------------------------------
    def execute(self) -> int:
        try:
            try:
                self._prepare()
            except StartFailed as failure:
                return self._start_failed(failure)
            except Exception as exc:  # noqa: BLE001
                return self._internal(exc)
            try:
                return self._serve()
            except Exception as exc:  # noqa: BLE001
                return self._internal(exc)
        finally:
            self._cleanup()

    def trace(self, type: str, data: Optional[dict] = None) -> None:
        if self.writer is not None and not self.writer.closed:
            try:
                self.writer.trace(type, data)
            except (EventError, OSError):
                pass

    # ---- failing before the run exists ----------------------------------------------------------------------------------
    def _start_failed(self, failure: StartFailed) -> int:
        outcome = clip(f"could not start: {failure.reason}", 2000)
        _stderr(outcome)
        if failure.chat and self.paths is not None:
            self._chat_system_line(failure.reason)
        self._emit_ended("crashed", outcome, "start_failed")
        return failure.exit_code

    def _internal(self, exc: BaseException) -> int:
        import traceback
        _stderr("engine host: internal error\n" + "".join(traceback.format_exception(exc)))
        if self.run is not None:
            self.stopping.set()
        self._emit_ended("crashed", clip(f"Crashed: {type(exc).__name__}: {exc}", 2000), "internal")
        return EXIT_INTERNAL

    def _emit_ended(self, status: str, outcome: str, code: Optional[str]) -> None:
        """`run.ended`, once, the last line. Best effort: a closed or missing writer is only a stderr line."""
        if self._ended:
            return
        self._ended = True
        if self.writer is None:
            return
        try:
            self.writer.emit(run_ended_event(status=status, outcome=outcome, code=code))
        except (EventError, OSError) as exc:
            _stderr(f"engine host: run.ended not written: {exc}")

    def _chat_system_line(self, text: str) -> None:
        """A `system` line in `chat.jsonl` without a `J2Run` (the preflight failed before J2 was imported)."""
        path = self.paths.run_dir / "chat.jsonl"
        lines = []
        if not path.exists():
            chosen = self.settings.output if self.settings and self.settings.output != "auto" else "website"
            lines.append({"meta": True, "run": self.paths.run_id[3:], "output": chosen,
                          "j2_fixes": int(self.settings.fixes) if self.settings else 0, "force_audit_fail": None,
                          "force_question": None, "test_lessons": None,
                          "realization": int(self.settings.realization) if self.settings else 1, "provider": None,
                          "model": None, "mock": False})
        lines.append({"id": 1, "t": time.strftime("%H:%M:%S"), "who": "system", "text": f"Could not start: {text}", "step": 0})
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.writelines(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
        except OSError as exc:
            _stderr(f"engine host: chat.jsonl not written: {exc}")

    # ---- steps 1 to 6: before the run exists --------------------------------------------------------------------------
    def _prepare(self) -> None:
        self._locate()
        self._read_task()
        self._settings_and_env()
        self._make_port()
        self._make_run()

    def _locate(self) -> None:
        run_dir = Path(os.path.abspath(self.args.run_dir))
        try:
            self.paths = DataPaths.from_run_dir(run_dir)
        except (RunDirError, ValueError) as exc:
            if (run_dir / EventWriter.EVENTS_NAME).is_file():       # the folder is foreign but the orchestrator's file is there
                try:
                    self.writer = EventWriter(run_dir)
                except OSError:
                    pass
            raise StartFailed(str(exc), EXIT_BAD_TASK) from None
        try:
            self.writer = EventWriter(self.paths.run_dir)
        except OSError as exc:
            raise StartFailed(f"events.jsonl cannot be opened: {exc}", EXIT_BAD_TASK) from None

    def _read_task(self) -> None:
        try:
            text = self.paths.task_json.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise StartFailed(f"task.json cannot be read: {exc}", EXIT_BAD_TASK) from None
        try:
            task = TaskSpec.model_validate_json(text)
        except ValidationError as exc:
            why = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'task'}: {e['msg']}" for e in exc.errors(include_url=False))
            raise StartFailed(f"task.json is invalid: {clip(why, 300)}", EXIT_BAD_TASK) from None
        if task.run_id != self.paths.run_id:
            raise StartFailed(f"task.json is for run {task.run_id}, not for the folder {self.paths.run_id}", EXIT_BAD_TASK)
        if task.dept_id != self.paths.dept_id:
            raise StartFailed(f"task.json is for department {task.dept_id}, not for the folder's {self.paths.dept_id}", EXIT_BAD_TASK)
        self.task = task
        if task.dropped_settings:
            self.trace("task.settings_dropped", {"keys": list(task.dropped_settings)})

    def _settings_and_env(self) -> None:
        paths, task = self.paths, self.task
        load_env_file()
        try:
            self.settings = EngineSettings.layered(os.environ, read_settings_file(paths.engine_json),
                                                   read_settings_file(paths.dept_engine_json), task.settings)
        except SettingsError as exc:
            raise StartFailed(f"settings: {exc}") from None
        self.mock = bool(self.args.mock or llm.env_mock() or task.connector == "stub")
        self._choose_output()
        try:
            _atomic_write(paths.settings_json, json.dumps(self.settings.model_dump(), indent=2) + "\n")
        except OSError as exc:
            raise StartFailed(f"settings.json cannot be written: {exc}") from None
        os.environ.update(self.settings.to_env())
        os.environ.update(paths.j2_env())
        if self.mock:
            os.environ["STUDIO_MOCK"] = "1"
        try:
            self._seed_library()
        except OSError as exc:
            raise StartFailed(f"the template library cannot be set up: {exc}") from None

    # ---- the output: `auto` is decided here, once, before J2 is imported (D129) ------------------------------------------------
    def _has_folder(self) -> bool:
        """True when the owner has set a working folder that is still usable (the same store the router reads per call)."""
        try:
            from sutra_app.connectors.workdir import WorkFolder      # read only: nothing is created in the data folder (the work root is not asked)
            return WorkFolder(self.paths.data_dir).get() is not None
        except Exception:  # noqa: BLE001 - no connector layer or an unreadable file is "no folder", never a failed start
            return False

    def _seed_output(self) -> Optional[str]:
        """The output of the finished run this task continues (`seed_from`), or None: not a follow-up, or its run cannot be read.
        The same checks as `_seed`: a run of this department, not a link, not this very run."""
        seed = self.task.seed_from
        if not seed:
            return None
        source = self.paths.runs_dir / seed
        if source.is_symlink() or not source.is_dir() or source == self.paths.run_dir:
            return None
        found = None
        for name, pick in (("chat.jsonl", lambda row: row.get("output")), ("summary.json", lambda row: row.get("output_type"))):
            try:
                text = (source / name).read_text(encoding="utf-8")
                row = json.loads(text.splitlines()[0]) if name == "chat.jsonl" else json.loads(text)
                found = pick(row) if isinstance(row, dict) else None
            except (OSError, ValueError, IndexError):
                continue
            if found in OUTPUT_NAMES and found != "auto":
                return found
        return None

    def _choose_output(self) -> None:
        """Replace `auto` by the concrete output (`capabilities.select_output`, a pure rule table: no model call), fix the settings that output
        needs (`capabilities.forced_settings`), and keep the decision: `self.selection` for the run's chat, `<run>/output.json` and one trace
        line."""
        from .. import capabilities
        task, settings = self.task, self.settings
        has_folder = self._has_folder()
        context = capabilities.EngineContext(task=task, settings=settings, paths=self.paths, data_dir=self.paths.data_dir,
                                             has_folder=has_folder, seed_output=self._seed_output())
        selection = capabilities.select_output(task.user_text, context)
        forced = {name: value for name, value in capabilities.forced_settings(selection.output).items()
                  if getattr(settings, name, value) != value}
        self.settings = settings.model_copy(update={"output": selection.output, **forced})
        self.selection, self.has_folder = selection, has_folder
        record = {"choice": settings.output, "output": selection.output, "rule": selection.rule, "reason": selection.reason,
                  "folder": has_folder}
        try:
            _atomic_write(self.paths.run_dir / "output.json", json.dumps(record, indent=2) + "\n")
        except OSError as exc:
            self.trace("publish.error", {"where": "output.json", "error": clip(str(exc), 300)})
        self.trace("output.selected", {**record, "forced": forced})

    def _seed_library(self) -> None:
        """Copy the seed template library to `<data>/library` once. Two processes may start together: each copies to its own
        temp folder and the rename decides (the loser deletes its copy)."""
        target = self.paths.library_dir
        if target.exists():
            return
        seed = Path(__file__).resolve().parent.parent / "seed" / "library"
        if not seed.is_dir():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".library.seed-{os.getpid()}")
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(seed, tmp)
        try:
            oslayer.replace(tmp, target)
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
            if not target.exists():
                raise

    def _make_port(self) -> None:
        paths, task = self.paths, self.task
        overhead = overhead_atom_id(task.run_id)
        self.sink = EventUsageSink(self.writer, default_atom=overhead)
        try:
            if self.make_port is not None:
                self.port = self.make_port(sink=self.sink, mock=self.mock, task=task, paths=paths)
            elif self.mock:
                self.port = llm.ScriptedPort(usage_sink=self.sink)
            else:
                self.port = self._connector_port()
            if not self.mock:
                result = self.port.preflight()
                if not result.ok:
                    raise StartFailed(result.message or "the model is not available", EXIT_START_FAILED, chat=True)
        except StartFailed:
            raise
        except ModelError as exc:
            raise StartFailed(f"{type(exc).__name__}: {exc}", EXIT_START_FAILED, chat=True) from None
        llm.configure(self.port, mock=self.mock, base_tag=CallTag(run_id=task.run_id, dept_id=task.dept_id, task_id=task.task_id))
        llm.bind_atom(overhead)                  # a call made before the first turn carries the run overhead key

    def _connector_port(self):
        try:
            from sutra_app.connectors.engine_port import make_port
        except ImportError as exc:
            raise StartFailed(f"the model connectors are not available ({exc})") from None
        spec = PortSpec(mock=False, connector=self.task.connector, run_id=self.task.run_id, dept_id=self.task.dept_id,
                        task_id=self.task.task_id, data_dir=str(self.paths.data_dir))
        return make_port(spec, usage_sink=self.sink)

    def _hooks_off(self, target: str, exc: BaseException) -> None:
        """The hook layer could not be built: the `publish.error` trace line and, for the owner, a `system` line in the chat."""
        reason = clip(f"{type(exc).__name__}: {exc}", 300)
        self.trace("publish.error", {"where": "hooks", "error": reason, "target": target})
        self._function_nodes_off = reason

    def _make_hooks(self, notify: Callable[[], None]):
        """`SUTRA_NODES=off` selects `EventHooks`; else the factory named by `SUTRA_HOOKS` (default: the function-node layer).
        An import error falls back to `EventHooks` with one `publish.error` trace line and, once the run exists, a `system`
        line "function nodes are off: <reason>"; a factory `ValueError` is 'could not start'."""
        try:
            validator = load_validator()
        except (ValueError, ImportError) as exc:
            raise StartFailed(f"records hook: {exc}") from None
        context_file = self.paths.run_dir / "node_context.json"

        def plain():
            return EventHooks(self.writer, notify, validator, context_file)

        if (os.environ.get("SUTRA_NODES") or "on").strip().lower() == "off":
            return plain()
        target = (os.environ.get("SUTRA_HOOKS") or DEFAULT_HOOKS).strip()
        try:
            if not _HOOK_RE.fullmatch(target):
                raise ImportError(f"SUTRA_HOOKS must look like package.module:function, not {target[:80]!r}")
            module, _, attr = target.partition(":")
            factory = getattr(importlib.import_module(module), attr)
        except (ImportError, AttributeError) as exc:
            self._hooks_off(target, exc)
            return plain()
        try:
            return factory(writer=self.writer, notify=notify, validator=validator, node_context_file=context_file, spec=self.task)
        except ValueError as exc:
            raise StartFailed(f"hooks: {exc}") from None
        except Exception as exc:  # noqa: BLE001
            self._hooks_off(target, exc)
            return plain()

    def _make_run(self) -> None:
        from .publisher import HostHooks, StatePublisher           # these import J2: the environment is set by now
        task, paths = self.task, self.paths
        from .. import capabilities, j2
        capabilities.register(j2)                                  # D126: the engine's own outputs, before any J2Run exists
        self.context = capabilities.EngineContext(task=task, settings=self.settings, paths=paths, data_dir=paths.data_dir,
                                                  selection=self.selection, has_folder=self.has_folder)
        capabilities.install(self.context)                         # the tag and progress hooks every model call of this process runs
        self.publisher = StatePublisher(self.writer, paths.run_dir)
        self.hooks = HostHooks(self._make_hooks(self.publisher.notify), self.publisher, self.context)
        self.run = j2.J2Run(run_dir=str(paths.run_dir), run_id=task.run_id[3:], hooks=self.hooks)
        self.context.run = self.run
        self.publisher.attach(self.run)
        self.hooks.run_started(task.model_dump())
        self.inbox = Inbox(paths.inbox, self.trace)

    # ---- steps 7 to 9: the seed, the first lines, the start ---------------------------------------------------------------
    def _seed(self) -> tuple[str, list[str]]:
        """('none' | 'rehydrated' | 'fresh', the system lines to post). Runs before any line of the host is posted."""
        from .. import rehydrate as rh            # the module J2Run.rehydrate uses: its RehydrateRefused is the one to catch
        task, paths = self.task, self.paths
        if not task.seed_from:
            return "none", []
        source = paths.runs_dir / task.seed_from
        if source.is_symlink() or not source.is_dir() or source == paths.run_dir:
            self.trace("seed.skipped", {"seed_from": task.seed_from, "reason": "not a run of this department"})
            return "fresh", []
        try:
            self.run.rehydrate(str(source))
        except rh.RehydrateRefused as refused:
            self.trace("seed.refused", {"seed_from": task.seed_from, "reason": refused.reason})
            self._copy_seed_files(source, paths.upstream_dir / task.seed_from)
            return "fresh", [rh.fresh_line(task.seed_from, refused.reason)]
        return "rehydrated", [rh.continuing_line(task.seed_from)]

    def _copy_seed_files(self, source: Path, dest: Path) -> None:
        """The old run's site, documents and key records go to `upstream/<old run id>/` (symbolic links are never followed)."""
        def copy(src: Path, rel: str) -> None:
            if src.is_symlink() or not src.is_file() or src.stat().st_size > UPSTREAM_MAX_BYTES:
                return
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)

        try:
            for entry in sorted(source.iterdir(), key=lambda p: p.name):
                if entry.name in HOST_FILES or entry.is_symlink():
                    continue
                if entry.is_file() and (entry.name in SEED_FILES or entry.suffix in SEED_SUFFIXES):
                    copy(entry, entry.name)
                elif entry.is_dir() and entry.name in SEED_TREES:
                    for sub in sorted(entry.rglob("*")):
                        if not any(part.is_symlink() for part in [sub, *sub.parents][: len(sub.relative_to(entry).parts) + 1]):
                            copy(sub, str(sub.relative_to(source)))
        except OSError as exc:
            self.trace("seed.refused", {"seed_from": self.task.seed_from, "reason": f"files not copied: {exc}"})

    def _upstream_line(self) -> Optional[str]:
        """Copy each upstream file to `upstream/<run id>/` and list them in one line. A path that is absolute, holds `..`, runs
        through a symbolic link or leaves the upstream run's folder is refused (one `upstream.skipped` trace line)."""
        parts = []
        for entry in self.task.upstream:
            run_id = entry.get("run_id")
            dept_id = entry.get("dept_id") or self.paths.dept_id
            if not run_id:
                continue
            root = self.paths.data_dir / "departments" / dept_id / "runs" / run_id
            copied = []
            for rel in entry.get("files") or []:
                reason = self._copy_upstream_file(root, run_id, rel)
                if reason:
                    self.trace("upstream.skipped", {"run_id": run_id, "file": clip(str(rel), 200), "reason": reason})
                else:
                    copied.append(rel)
            if copied:
                parts.append(f"{entry.get('title') or run_id} (run {run_id}): {', '.join(copied)}")
        if not parts:
            return None
        return clip("Earlier work from other teams is in upstream/<run id>/ for reference. " + "; ".join(parts), 1500)

    def _copy_upstream_file(self, root: Path, run_id: str, rel: Any) -> Optional[str]:
        """None when the file was copied, else why not."""
        if not isinstance(rel, str) or not rel or "\x00" in rel:
            return "not a file path"
        pure = PurePosixPath(rel)
        if pure.is_absolute() or ".." in pure.parts or any(part in ("", ".") for part in rel.split("/")[:-1]):
            return "absolute or '..' path"
        if root.is_symlink() or not root.is_dir():
            return "the upstream run folder does not exist"
        current = root
        for part in pure.parts:
            current = current / part
            if current.is_symlink():
                return "a symbolic link"
        try:
            if not current.is_file():
                return "not a file"
            if current.stat().st_size > UPSTREAM_MAX_BYTES:
                return "larger than 20 MB"
            if os.path.commonpath([os.path.realpath(current), os.path.realpath(root)]) != os.path.realpath(root):
                return "leaves the run folder"
            target = self.paths.upstream_dir / run_id / pure
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(current, target)
        except OSError as exc:
            return f"cannot be copied: {exc}"
        return None

    def _serve(self) -> int:
        task, run = self.task, self.run
        seed, lines = self._seed()
        self.writer.emit(run_started_event(pid=os.getpid(), mock=self.mock, seed=seed))
        self.heartbeat = Heartbeat(self.writer, heartbeat_interval())
        self.heartbeat.start()                     # the first beat follows run.started at once
        if self.selection is not None:
            from ..capabilities.select import chat_line
            said = chat_line(self.selection, self.has_folder)
            if said:                                   # project work only: a website selection posts nothing, so existing runs are unchanged
                lines.append(said)
        if self._function_nodes_off:
            lines.append(f"function nodes are off: {self._function_nodes_off}")
        if task.framing.strip():
            lines.append(f"Context from the team lead: {task.framing.strip()}")
        upstream = self._upstream_line()
        if upstream:
            lines.append(upstream)
        for line in lines:
            run.post("system", line)
        self._install_handlers()
        self.publisher.publish(force=True)
        self.publisher.start()
        if not run.user_says(task.user_text):
            raise RuntimeError("the run did not take the first message")
        while True:
            code = self._tick()
            if code is not None:
                return code
            self._terminate.wait(TICK_S)

    # ---- one tick ---------------------------------------------------------------------------------------------------------
    def _tick(self) -> Optional[int]:
        run = self.run
        if self._terminate.is_set():
            return self._stop_run(TERM_OUTCOME, EXIT_TERM)
        stop = self.inbox.poll()
        if stop is not None:
            self.trace("inbox.stop", {"n": stop.n})
            return self._stop_run(STOP_OUTCOME, EXIT_OK)
        self._watch_thread()
        self.inbox.deliver(run)
        if self._finished():
            stop = self.inbox.poll()                  # one more look before the run is declared over
            self.inbox.deliver(run)
            if stop is not None:
                self.trace("inbox.stop", {"n": stop.n, "late": True})
            if self._finished():
                return self._end_normally()
        return None

    def _finished(self) -> bool:
        run = self.run
        return run.status == "waiting" and not run.paused and not run.lock.locked() and not len(self.inbox)

    def _watch_thread(self) -> None:
        """A run thread that dies without finishing (SystemExit, or an exception `_run_safe` did not catch) leaves the status
        `running`: the thread excepthook records the exception; a silent death is seen as `running` with a free run lock."""
        run = self.run
        if run.status != "running":
            self._dead_since = None
            self._thread_exc = None
            return
        if self._thread_exc is not None:
            return self._crash(self._thread_exc)
        if run.lock.locked():
            self._dead_since = None
            return
        now = time.monotonic()
        if self._dead_since is None:
            self._dead_since = now
        elif now - self._dead_since >= DEAD_THREAD_GRACE_S:
            self._crash(RuntimeError("the run thread ended without finishing"))

    def _crash(self, exc: BaseException) -> None:
        """Path c of F7: set what `_run_safe` would have set, so the run ends as crashed."""
        run = self.run
        message = clip(f"{type(exc).__name__}: {exc}", 300)
        self.trace("thread.died", {"error": message})
        run.error = message
        for step in (lambda: run.post("system", f"Stopped: {message}"),
                     lambda: self.hooks.run_error("internal", message)):
            try:
                step()
            except Exception as err:  # noqa: BLE001
                self.trace("publish.error", {"where": "crash", "error": clip(f"{type(err).__name__}: {err}", 300)})
        run.outcome = f"Crashed: {message}"
        try:
            run._write_summary()
        except Exception as err:  # noqa: BLE001
            self.trace("publish.error", {"where": "crash summary", "error": clip(f"{type(err).__name__}: {err}", 300)})
        run.turn, run.status = None, "waiting"
        self._thread_exc, self._dead_since = None, None
        try:
            run._run_status()
        except Exception:  # noqa: BLE001
            pass

    # ---- the ends ---------------------------------------------------------------------------------------------------------
    def _end_normally(self) -> int:
        run = self.run
        status = outcome_status(run.outcome)
        code = None
        if status == "crashed":
            code = getattr(self.hooks, "error_code", None) or "internal"
        self._conclude(status, run.outcome or "", code)
        return EXIT_OK

    def _stop_run(self, outcome: str, exit_code: int) -> int:
        """A stop line or SIGTERM (F5): `stopping` is set before the port is closed, so nothing waits on a model; the run
        thread is given a few seconds; the outcome and `summary.json` say stopped; one more publish; `run.ended{stopped}`."""
        run = self.run
        self.stopping.set()
        try:
            run.stopping = True                    # J2Run's crash path skips the reviewer call and the report when it reads this
        except Exception:  # noqa: BLE001
            pass
        self._close_port()
        deadline = time.monotonic() + STOP_WAIT_S
        while time.monotonic() < deadline and (run.status == "running" or run.lock.locked()):
            time.sleep(0.02)
        run.error = None
        run.outcome = outcome
        try:
            run.post("system", outcome + ".")
        except Exception as err:  # noqa: BLE001
            self.trace("publish.error", {"where": "stop post", "error": clip(f"{type(err).__name__}: {err}", 300)})
        run.turn, run.paused, run.status, run.done = None, None, "waiting", True
        self._abandon_open_atoms()
        self._write_stopped_summary(outcome)
        self._conclude("stopped", outcome, None)
        return exit_code

    def _abandon_open_atoms(self) -> None:
        """A stop or SIGTERM sends no `run_status` hook, so the layer is told here: no atom is open at `run.ended`. The plain
        `EventHooks` have no atoms and no such method."""
        abandon = getattr(self.hooks, "abandon_open", None)
        if abandon is None:
            return
        try:
            abandon("stopped")
        except Exception as err:  # noqa: BLE001
            self.trace("publish.error", {"where": "abandon_open", "error": clip(f"{type(err).__name__}: {err}", 300)})

    def _write_stopped_summary(self, outcome: str) -> None:
        try:
            self.run._write_summary()              # code only; the outcome starts with "Stopped", so its status is stopped
            return
        except Exception as err:  # noqa: BLE001
            self.trace("publish.error", {"where": "stop summary", "error": clip(f"{type(err).__name__}: {err}", 300)})
        path = self.paths.run_dir / "summary.json"
        try:
            summary = json.loads(path.read_text(encoding="utf-8"))
            summary = summary if isinstance(summary, dict) else {}
        except (OSError, ValueError):
            summary = {"run": self.run.run_id}
        try:
            _atomic_write(path, json.dumps({**summary, "status": "stopped", "outcome": outcome}, indent=2, ensure_ascii=False))
        except OSError as err:
            self.trace("publish.error", {"where": "stop summary file", "error": clip(str(err), 300)})

    def _conclude(self, status: str, outcome: str, code: Optional[str]) -> None:
        """Final publish, then `run.ended`: the publisher and the heartbeat are stopped first, so nothing follows it."""
        self.inbox.close()
        self.publisher.stop()
        self.heartbeat.stop()
        try:
            self.publisher.final()
        except Exception as err:  # noqa: BLE001
            self.trace("publish.error", {"where": "final", "error": clip(f"{type(err).__name__}: {err}", 300)})
        self._emit_ended(status, clip(outcome, 2000), code)

    def _close_port(self) -> None:
        try:
            if self.port is not None:
                self.port.close()
        except Exception as err:  # noqa: BLE001
            self.trace("publish.error", {"where": "port.close", "error": clip(f"{type(err).__name__}: {err}", 300)})

    # ---- signals and threads --------------------------------------------------------------------------------------------
    def _install_handlers(self) -> None:
        self._saved_hook = threading.excepthook

        def hook(args):
            if args.thread is not None and args.thread.name.startswith("sutra-"):
                return self._saved_hook(args)
            self._thread_exc = args.exc_value
            self._saved_hook(args)

        threading.excepthook = hook
        if threading.current_thread() is threading.main_thread():
            self._saved_sigterm = signal.signal(signal.SIGTERM, self.request_termination)

    def request_termination(self, *_args) -> None:
        """SIGTERM: close the model port now (that kills child CLIs and wakes a run thread that waits on a model); the main
        loop then ends the run as stopped and exits 143."""
        self.stopping.set()
        self._close_port()
        self._terminate.set()

    def _cleanup(self) -> None:
        if self._saved_hook is not None:
            threading.excepthook = self._saved_hook
            self._saved_hook = None
        if self._saved_sigterm is not None and threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self._saved_sigterm)
            self._saved_sigterm = None
        if self.inbox is not None:
            self.inbox.close()
        if self.publisher is not None:
            self.publisher.stop()
        if self.heartbeat is not None:
            self.heartbeat.stop()
        self._close_port()
        if self.writer is not None:
            self.writer.close()
