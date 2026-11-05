"""The check runner of the function-node layer (function-nodes.md sections 4 and 5; engine design 4.3a).

The registry (`registry.py`, WP E8) holds the 14 pure checks and reads an `Evidence` bundle. This module is the other half:

    TurnBuffer     what the hooks hand the layer during one function turn, copied at hook time (J2 passes live lists and
                   dicts, which it keeps changing): the node's calls and replies, the messages posted (each tagged with
                   `after_reply`, how many replies had arrived), the record files saved, the files as read at turn start
    CheckRunner    builds the `Evidence` from a buffer, runs the declared checks of an atom for one PHASE and turns every
                   `Outcome` into the library's `CheckResult` (exit 0 passed or does not apply, 1 failed, 127 could not run)
    Round          the results of one run of all the atom's checks, and what to do with them (`passed`, `reason`)

Phases. `reply`: a reply of the node just arrived; the checks whose registry phases include `reply` are judged, every other
check answers `deferred: judged when the turn ends` with exit 0 (the try is only as good as what could be judged). `turn`
and `event`: the turn ended, or the event a check waits for arrived; EVERY declared check is judged on the whole turn
(a reply-phase check is judged again on the turn's last reply, because the library wants one result per check and try).

How an Outcome becomes a result (the reading E8 documents): ok is exit 0; ok with `changed` means J2's own code repaired,
templated or dropped something and the evidence starts `RECOVERED: `; ok with `waived` means J2 accepted a concern on
record and the evidence starts `WAIVED: `; ok with `na` is exit 0 with the check's own words; not ok is exit 1. A check that
cannot run at all (an unknown name, the wrong number of arguments, an exception, evidence that cannot be built) is exit 127
and the evidence says why: a missing runner is a failed attempt, never a silent pass.
"""
import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Optional

from sutra_app.engine.hooks import CallInfo, TurnInfo, TurnOutcome
from sutra_app.library.atom import EXIT_FAIL, EXIT_MISSING, EXIT_PASS, MAX_ATTEMPTS, Atom, CheckResult
from sutra_app.library.types import clip

from .evidence import RECORD_NAMES, Evidence, merge_records
from .registry import REGISTRY, Outcome

__all__ = ["Phase", "DEFERRED", "RECOVERED", "WAIVED", "TurnBuffer", "CheckRun", "Round", "CheckRunner"]

Phase = Literal["reply", "turn", "event"]
DEFERRED: Final = "deferred: judged when the turn ends"
RECOVERED: Final = "RECOVERED: "
WAIVED: Final = "WAIVED: "
EVIDENCE_MAX: Final = 2000
REASON_MAX: Final = 600
REASON_PREFIX: Final = "verify failed: "


@dataclass
class TurnBuffer:
    """Everything the hooks saw of one function turn. The layer fills it; `CheckRunner.evidence` reads it."""

    turn: TurnInfo
    before: dict[str, Any] = field(default_factory=dict)       # the record files as read at turn start (`read_records`)
    calls: list[CallInfo] = field(default_factory=list)       # the node's own agent_turn calls
    replies: list[dict] = field(default_factory=list)         # their replies that are objects, oldest first
    posted: list[dict] = field(default_factory=list)          # messages since the turn started, with `after_reply`
    records: dict[str, Any] = field(default_factory=dict)     # the check records saved this turn
    saved: list[str] = field(default_factory=list)            # every record name saved this turn, in order
    owners: dict[str, str] = field(default_factory=dict)      # atom id -> owner node
    question: Optional[dict] = None                           # the ASK_REQUESTER message this turn posted: {id, text, pause}

    @property
    def model(self) -> Optional[str]:
        """The model of the first call, which stamps the atom."""
        return next((c.model for c in self.calls if c.model), None)

    def add_call(self, call: CallInfo) -> None:
        self.calls.append(call)
        if isinstance(call.reply, dict):
            self.replies.append(copy.deepcopy(call.reply))

    def add_message(self, message: Mapping) -> dict:
        posted = {**copy.deepcopy(dict(message)), "after_reply": len(self.replies)}
        self.posted.append(posted)
        return posted

    def add_record(self, name: str, data: Any) -> None:
        self.saved.append(name)
        if name in RECORD_NAMES:
            self.records[name] = copy.deepcopy(data)


@dataclass(frozen=True)
class CheckRun:
    """One check's result in a round, with the Outcome it came from (None when the check was deferred or could not run)."""

    name: str
    result: CheckResult
    outcome: Optional[Outcome] = None
    deferred: bool = False

    @property
    def passed(self) -> bool:
        return self.result.exit_code == EXIT_PASS


@dataclass(frozen=True)
class Round:
    """The results of running all the checks of an atom once, one per check, in the atom's order."""

    runs: tuple[CheckRun, ...]

    @property
    def results(self) -> list[CheckResult]:
        return [run.result for run in self.runs]

    @property
    def passed(self) -> bool:
        return all(run.passed for run in self.runs)

    @property
    def failing(self) -> list[CheckRun]:
        return [run for run in self.runs if not run.passed]

    @property
    def concerns(self) -> list[str]:
        """The checks that passed with a concern on record (RECOVERED or WAIVED)."""
        return [run.name for run in self.runs if run.passed and run.result.evidence.startswith((RECOVERED, WAIVED))]

    @property
    def reason(self) -> str:
        """The abandon reason of a round that failed: `verify failed: <check>: <evidence>` for each failing check."""
        parts = [f"{run.name}: {run.result.evidence or 'exit ' + str(run.result.exit_code)}" for run in self.failing]
        return clip(REASON_PREFIX + "; ".join(parts), REASON_MAX)


class CheckRunner:
    """Runs the declared checks of an atom. `registry` is the E8 `REGISTRY` (a stand-in with the same three members
    `__contains__`, `__getitem__` and `run` serves the tests)."""

    def __init__(self, registry: Any = REGISTRY) -> None:
        self.registry = registry

    # ---- evidence ---------------------------------------------------------------------------------------------------
    def evidence(self, buf: TurnBuffer, *, outcome: Optional[TurnOutcome] = None) -> Evidence:
        """The bundle a check reads, from a buffer. `outcome` is None until the turn has ended. When the node's latest call
        gave no usable reply the bundle holds no replies at all, so `reply-valid` says so instead of judging an older reply."""
        call = buf.calls[-1] if buf.calls else None
        replies = [] if call is not None and not isinstance(call.reply, dict) else copy.deepcopy(buf.replies)
        return Evidence(
            turn=buf.turn, outcome=outcome, reply=None, replies=replies, call=call, posted=copy.deepcopy(buf.posted),
            records=merge_records(buf.before, buf.records), before=copy.deepcopy(buf.before), owners=dict(buf.owners),
            saved=tuple(buf.saved))

    # ---- one round --------------------------------------------------------------------------------------------------
    def round(self, atom: Atom, buf: TurnBuffer, phase: Phase, now: int, *, outcome: Optional[TurnOutcome] = None) -> Round:
        """Run every check of `atom` once, for the close run `atom.attempt + 1`, and return the results in order."""
        number = atom.attempt + 1
        if number > MAX_ATTEMPTS:
            raise ValueError(f"atom {atom.id} has used all {MAX_ATTEMPTS} close runs: abandon it instead of running more checks")
        try:
            ev: Optional[Evidence] = self.evidence(buf, outcome=outcome if phase != "reply" else None)
            broken = ""
        except Exception as exc:                  # a bundle that cannot be built fails every check, visibly
            ev, broken = None, f"the evidence could not be built: {type(exc).__name__}: {exc}"
        runs = []
        for check in atom.verify.checks:
            name = check.template
            if broken:
                runs.append(self._missing(name, number, now, broken))
            elif name not in self.registry:
                runs.append(self._missing(name, number, now, f"no runner for the check {name!r}"))
            elif phase == "reply" and "reply" not in self.registry[name].phases:
                runs.append(CheckRun(name, CheckResult(attempt=number, exit_code=EXIT_PASS, evidence=DEFERRED, ts=now), deferred=True))
            else:
                runs.append(self._run(name, ev, tuple(check.args), number, now))
        return Round(tuple(runs))

    def _run(self, name: str, ev: Evidence, args: tuple[str, ...], number: int, now: int) -> CheckRun:
        try:
            outcome = self.registry.run(name, ev, args)
        except Exception as exc:                  # UnknownCheck, CheckArgsError, or a check that is itself broken
            return self._missing(name, number, now, f"the check {name} could not run: {type(exc).__name__}: {exc}")
        return CheckRun(name, CheckResult(attempt=number, exit_code=EXIT_PASS if outcome.ok else EXIT_FAIL,
                                          evidence=self.words(outcome), ts=now), outcome)

    @staticmethod
    def _missing(name: str, number: int, now: int, why: str) -> CheckRun:
        return CheckRun(name, CheckResult(attempt=number, exit_code=EXIT_MISSING, evidence=clip(why, EVIDENCE_MAX), ts=now))

    @staticmethod
    def words(outcome: Outcome) -> str:
        """The evidence text of an Outcome: `RECOVERED: ` or `WAIVED: ` in front when J2 repaired or accepted something."""
        text = outcome.evidence
        if outcome.ok and outcome.waived:
            text = WAIVED + text
        elif outcome.ok and outcome.changed:
            text = RECOVERED + text
        return clip(text, EVIDENCE_MAX)
