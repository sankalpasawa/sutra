"""The steps at the end of a run: the agent-readable JSON and the template catalog (J2 sync 4, D142 and D143).

    finish.run_steps(host, status)

`Host._conclude` calls it once, right after the publisher stopped and before the heartbeat does: the heartbeat still beats while the steps
work, and the final publish and `run.ended` come after every file they write. A run that ended `done` or `done_with_open_items` gets the
steps below, in this order (a node's `handoff` first, G1); a stopped or crashed run gets none.

    agent_views   `j2_agent_views.build(<run folder>, quiet=True)`: the agent-readable JSON (`agent/*.json`, `artifacts/<name>.json`,
                  `site/sections/<id>.json`, the stamped `prd.json`, `hld.json`, `lld.json`, `design.json`) that the Artifacts pane's
                  Agent-readable tab shows, each file checked by its model. J2 builds them only by hand
                  (`python -m sutra_app.engine.j2_agent_views build <run folder>`).
    handoff       `handoff.json`, only for a node of a multi-agent project (the optional `node` block of `task.json`, `NODE_STEPS`: any other run does not even get a trace line for it): the files of
                  the run folder with their checksums and the run's own outcome sentence, for the server to check and scrub (handoff.py).
    catalog       `j2_template_lib.collect(<team runs folder>, runs=[<this run>])` under the library lock (P10): the templates this run
                  stored reach the catalog. Only when the template library is on for the run (`EngineSettings.effective()`, D178: `auto_reuse` turns it on in J2 too), the run is not a mock run (a scripted
                  run teaches the library nothing) and it stored templates. A lock that stays taken for the whole wait skips the step.

The steps run in the engine process (D14: files only, the server never writes the library) and every one of them is guarded. An exception,
a `SystemExit` (`j2_agent_views.build` raises one for a folder that is not there) or a step that took more than `STEP_SECONDS` is traced
and never fails the run: the run ended well and stays ended well. A step over the limit also ends the rest (the limit is checked when a
step returns: a step cannot be cut short from outside without leaving a half-written file). The `finish.step` lines of `trace.jsonl`:

    {"step": "agent_views", "result": "ok", "seconds": 0.21, "files": 15, "valid": 14, "invalid": ["design.json"]}
    {"step": "catalog", "result": "skipped", "why": "a mock run teaches the library nothing", "seconds": 0.0}
    {"step": "catalog", "result": "failed", "error": "OSError: ...", "seconds": 0.02}
    {"step": ..., "result": ..., "seconds": 11.4, "slow": true}            # and every later step: "skipped", "why": "<step> took more than 10 s"

The J2 modules are imported inside the steps, never here: the host sets the J2 environment before J2 is first imported, and this module
is imported by `loop.py` before that.
"""
import time
from collections.abc import Callable
from typing import Any, Optional

from sutra_app.library.types import clip

from ..events import END_STATUSES

__all__ = ["run_steps", "agent_views", "catalog", "handoff", "Skip", "STEPS", "NODE_STEPS", "ENDED_WELL", "STEP_SECONDS", "TRACE_TYPE"]

ENDED_WELL = END_STATUSES[:2]                      # the `run.ended` statuses that get the steps (`done`, `done_with_open_items`): the statuses have one owner, events.py (D188, R-3)
STEP_SECONDS = 10.0                                # a step that takes longer ends the rest (D142)
TRACE_TYPE = "finish.step"


class Skip(Exception):
    """A step that does not apply to this run, or could not get what it needs. `why` is one plain sentence for the trace line."""

    def __init__(self, why: str):
        super().__init__(why)
        self.why = why


Step = Callable[[Any], Optional[dict]]


# ---- the steps: each takes the host and returns the facts for its trace line (or raises Skip) --------------------------------------

def agent_views(host) -> dict:
    """The agent-readable JSON of the run folder (D143). `build` reads the run's files and writes new JSON files; it writes through no
    `J2Run.save`, so no records gate sees it, and it runs after the run's last file was written."""
    from .. import j2_agent_views
    built = j2_agent_views.build(str(host.paths.run_dir), quiet=True)
    invalid = [str(row.get("path")) for row in built if not row.get("valid")]
    return {"files": len(built), "valid": len(built) - len(invalid), "invalid": invalid[:10]}


def catalog(host) -> dict:
    """This run's templates into the catalog (D142), under the library lock. `collect` writes `index.json` and version folders with no
    lock of its own (P10 wraps only `store` and `mark_used`), so the whole read-modify-write happens inside `_library_lock()`."""
    if not host.settings.effective().template_library:
        raise Skip("the template library is off for this run")
    if host.mock:
        raise Skip("a mock run teaches the library nothing")
    paths = host.paths
    if not (paths.run_dir / "templates.json").is_file():
        raise Skip("the run stored no templates")                  # nothing to collect: the library is neither locked nor rewritten
    from .. import j2_template_lib as library
    try:
        with library._library_lock():                              # P10: waits up to 30 s for another writer, then raises LibraryBusy
            report = library.collect(str(paths.runs_dir), runs=[paths.run_id])
    except library.LibraryBusy as busy:
        raise Skip(str(busy)) from None
    row = report[0] if report else {}
    return {key: len(row.get(key) or ()) for key in ("added", "renumbered", "same", "not_recorded")}


def handoff(host) -> dict:
    """`handoff.json` for a node of a multi-agent project (D263, MAN-6): what the run leaves for the server to check, scrub and store. Only when `task.json` has a `node` block: any other run
    skips it, so a run that is not a node writes nothing new. The files and checksums are read from the run folder here, never from what an agent said."""
    node = getattr(getattr(host, "task", None), "node", None)
    if node is None:
        raise Skip("the run is not a node of a project")
    from . import handoff as handoff_file
    document = handoff_file.build(host.paths.run_dir, node.id, getattr(host, "ended_status", "done"), getattr(host, "ended_outcome", ""))
    handoff_file.write(host.paths.run_dir, document)
    return {"files": len(document["files"]), "status": document["status"]}


STEPS: tuple[tuple[str, Step], ...] = (("agent_views", agent_views), ("catalog", catalog))
NODE_STEPS: tuple[tuple[str, Step], ...] = (("handoff", handoff),)       # added after `STEPS` for the run of a node only: any other run has the steps (and the trace lines) it always had (MAN-6)


# ---- the runner ------------------------------------------------------------------------------------------------------------------

def run_steps(host, status: str, steps: Optional[tuple[tuple[str, Step], ...]] = None, *,
              clock: Callable[[], float] = time.monotonic) -> list[dict]:
    """Run the steps for a run that ended `status`; returns the data of the `finish.step` lines it wrote (none for a run that did not end
    well). It never raises what a step raises: the caller is the end of a run, which must still be written."""
    if status not in ENDED_WELL:
        return []
    written: list[dict] = []
    slow: Optional[str] = None                                    # the name of the first step over the limit
    if steps is None:
        steps = (NODE_STEPS if getattr(getattr(host, "task", None), "node", None) is not None else ()) + STEPS     # a node's hand-off goes FIRST: a slow step must never cost it its hand-off (G1, D311)
    for name, step in steps:
        row: dict[str, Any] = {"step": name}
        asked_to_stop = getattr(host, "stopping", None)
        if slow is not None:
            row.update(result="skipped", why=f"{slow} took more than {STEP_SECONDS:g} s")
        elif asked_to_stop is not None and asked_to_stop.is_set():
            row.update(result="skipped", why="the process was asked to stop")
        else:
            started = clock()
            try:
                row.update(step(host) or {})
                row["result"] = "ok"
            except Skip as skip:
                row["result"], row["why"] = "skipped", skip.why
            except (Exception, SystemExit) as exc:                # noqa: BLE001 - SystemExit: j2_agent_views.build raises it for a missing folder
                row["result"], row["error"] = "failed", clip(f"{type(exc).__name__}: {exc}", 300)
            row["seconds"] = round(clock() - started, 3)
            if row["seconds"] > STEP_SECONDS:
                row["slow"], slow = True, name
        try:
            host.trace(TRACE_TYPE, row)
        except Exception:                                         # noqa: BLE001 - a trace line is never worth the end of a run
            pass
        written.append(row)
    return written
