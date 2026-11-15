"""The work atom: the plugin's GOAL / CONSTRAINTS / CONTEXT / WORK / VERIFY, its lifecycle, ledger row, card, and J2's
atom/1 view (library design section 7; S2-models-06, S4-fnodes-02, -03, -08, -09).

An atom declares a goal and the checks that will prove it BEFORE the work, and it closes only through passing checks.
One function turn is one atom (work `llm`, `bash` or `manual`); J2's re-asks inside the turn are its tries, at most 3.

    AtomDraft, Atom      what the layer declares / the stored record (family "atom", schema string `work-atom/0.3`)
    open_atom            a draft becomes an open atom, or a STORED refused atom (the plugin's rules, first one wins)
    close_atom           one result per check: all pass -> closed; else attempt + 1 and the atom stays open (VERIFY FAILED)
    abandon_atom         the layer (or the server) ends an open atom with a reason and a code; runs no check
    atom_display_state   the five words every surface shows: stored open / closed / refused / abandoned, plus verify_failed
                         (an atom abandoned with abandon_code "verify_failed"); `verify_failed` is NEVER stored
    ledger_row           the Atom log row of a terminal atom; ledger_row_from_view does the same for a J2 atom/1 view
    Card, Transition     every transition renders its card inside the transition; nobody can skip it
    AtomView, atom_view  J2's atom/1 document (the wire form builders keep), built from an Atom; run_views, link_views,
                         validate_views and friends are ports of j2_schema.py

Pure functions, no clock and no I/O: callers pass `now`, and a pinned test's current hash arrives as `pins_now`. The
argument rules of the 26 check names live in `check_arity`, which is bound to the registry at import so that
`REGISTRY.verify_refs()` can check the function specs' check references.
"""
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Annotated, Any, Final, Literal, NoReturn, Self, Union

from pydantic import Field, StringConstraints, ValidationError, model_validator
from pydantic_core import InitErrorDetails

from .base import Record, Value
from .registry import REGISTRY, record
from .types import AtomId, DomainEvent, JsonObject, NodeId, Ts, WorkflowId, clip

__all__ = [
    "MAX_ATTEMPTS", "EXIT_PASS", "EXIT_FAIL", "EXIT_PIN_CHANGED", "EXIT_MISSING", "CheckTemplate", "PLUGIN_CHECKS",
    "J2_CHECKS", "REGISTRY_CHECKS", "CHECK_NAMES", "BEHAVIOR_VERBS", "ATOM_DETAIL_KEYS", "AtomError", "check_arity",
    "default_relevance", "check_sentence", "Constraint", "Work", "ExpectedItem", "CheckResult", "Check", "Verify",
    "AtomEdge", "Refusal", "AtomDraft", "OutputItem", "REPLY_TEXT_MAX", "AtomReply", "Atom", "open_rules", "Seen", "CardRow", "Card",
    "Transition",
    "build_card", "card", "open_atom", "close_atom", "abandon_atom", "atom_display_state", "LedgerVerify", "LedgerRow",
    "ledger_row", "ledger_row_from_view", "ViewHow", "ViewCheck", "AtomView", "atom_view", "atom_kind", "dedupe_edges",
    "link_views", "dependency_edges", "run_views", "validate_atom", "validate_views", "MAKE_CHECKS", "DO_CHECKS",
    "FINAL_FORMS",
]

MAX_ATTEMPTS: Final = 3                      # close runs per atom (ADR-038 section 5, ADR-029 D4, J2 MAX_CHECK_ATTEMPTS)
EXIT_PASS, EXIT_FAIL, EXIT_PIN_CHANGED, EXIT_MISSING = 0, 1, 97, 127      # 97: pinned test changed (SA:325); 127: runner missing
PIN_EVIDENCE: Final = "hash-pin mismatch: the pinned test changed since the atom opened"
BANAL_GOAL_RE: Final = re.compile(r"(works|done|ok|fix|fixed|good|passes|it runs|no errors)", re.IGNORECASE)   # SA:36, fullmatch
_DIGITS_RE: Final = re.compile(r"[0-9]+")

Line200 = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Line300 = Annotated[str, StringConstraints(min_length=1, max_length=300)]
Line500 = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Text300 = Annotated[str, StringConstraints(max_length=300)]
Text600 = Annotated[str, StringConstraints(max_length=600)]
Text2000 = Annotated[str, StringConstraints(max_length=2000)]
Reason600 = Annotated[str, StringConstraints(min_length=1, max_length=600)]
Name60 = Annotated[str, StringConstraints(min_length=1, max_length=60)]
Id64 = Annotated[str, StringConstraints(min_length=1, max_length=64)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Problem = tuple[tuple[str | int, ...], str]       # (place inside the model, what is wrong)

# ---- the 26 check names -------------------------------------------------------------------------------------------
CheckTemplate = Literal[
    # the plugin's templates (SA:185, bin/verify-templates) and J2's check types (J2:321-323, atom-schema.md)
    "file-exists", "grep-count", "named-test",
    "element-count", "facts-present", "tap-targets", "behavior-steps", "heading-present", "section-not-empty",
    "ids-unique", "lld-slice", "deed-send",
    # the engine's verify registry: one pure function each (function-nodes.md section 4, S4-fnodes-02)
    "reply-valid", "turn-posted", "charter-stamp", "workable", "audience-split", "atom-rules", "judge-gate", "price-kept",
    "within-budget", "order-registered", "finding-per-item", "pass-needs-proof", "code-measure-wins", "answer-recorded",
]
PLUGIN_CHECKS: Final = ("file-exists", "grep-count", "named-test")
J2_CHECKS: Final = ("element-count", "facts-present", "tap-targets", "behavior-steps", "heading-present", "section-not-empty",
                    "ids-unique", "lld-slice", "deed-send")
REGISTRY_CHECKS: Final = ("reply-valid", "turn-posted", "charter-stamp", "workable", "audience-split", "atom-rules",
                          "judge-gate", "price-kept", "within-budget", "order-registered", "finding-per-item",
                          "pass-needs-proof", "code-measure-wins", "answer-recorded")
CHECK_NAMES: Final = (*PLUGIN_CHECKS, *J2_CHECKS, *REGISTRY_CHECKS)

# (fewest, most) arguments. The plugin's three: grep-count is (pattern, file, min), the other two take paths. J2's nine
# take their target(s). The registry's: reply-valid is [family, kind] ("a|b" lists kinds), answer-recorded is [question
# message id], the other twelve take none (S4-fnodes-02).
_ARITY: Final = {
    "file-exists": (1, 8), "grep-count": (3, 3), "named-test": (1, 8),
    **{name: (0, 8) for name in J2_CHECKS},
    "reply-valid": (2, 2), "answer-recorded": (1, 1),
    **{name: (0, 0) for name in REGISTRY_CHECKS if name not in ("reply-valid", "answer-recorded")},
}


def check_arity(name: str) -> tuple[int, int] | None:
    """(fewest, most) arguments of a named check, or None for a name that is not one of the 26."""
    return _ARITY.get(name)


REGISTRY.bind_check_arity(check_arity)       # REGISTRY.verify_refs() checks the function specs' check references with this


class AtomError(Exception):
    """A programming error: something the atom module cannot answer (the ledger row of an open atom, an unknown abandon
    code). Rule breaks by DATA are never this: they are a stored refused atom, a refused Transition or a ValidationError."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _raise(title: str, problems: Sequence[Problem]) -> NoReturn:
    """Fail validation with one error per problem, each at its own place (one ValueError could report only one)."""
    raise ValidationError.from_exception_data(title, [
        InitErrorDetails(type="value_error", loc=loc, input=None, ctx={"error": ValueError(text)}) for loc, text in problems])


# ---- the parts of an atom -----------------------------------------------------------------------------------------

class Constraint(Value):
    """What the work may not do; `check` is an optional sentence a check can use (the plugin sets it to null)."""

    text: Line300
    check: Text300 | None = None


class Work(Value):
    """How the atom is done: `dispatch_kind` is the plugin's, `how_kind` and `agent` are J2's `how` (J2:5126)."""

    dispatch_kind: Literal["llm", "skill", "bash", "manual"]
    ref: Annotated[str, StringConstraints(max_length=200)] | None = None
    agent: Annotated[str, StringConstraints(max_length=80)] | None = None
    steps: Text2000 = ""
    how_kind: Literal["AI", "code"] = "AI"


BEHAVIOR_VERBS: Final = ("set", "click", "scroll-to", "wait", "expect-visible", "expect-hidden", "expect-text",
                         "expect-number", "expect-changed", "expect-style-changed", "expect-class")      # J2:5145-5154
MAX_WAITS: Final = 3


class ExpectedItem(Value):
    """One thing that must exist when the atom is done (J2's `expected_output`, J2:5128-5129). `heading`, `ids` and `send`
    are the kinds J2's document and deed atoms use; `met` is what J2's code sets after the checks ran."""

    text: Line300
    kind: Literal["section", "element", "facts", "file", "test", "tap", "behavior", "heading", "ids", "send"]
    target: Union[Line300, Annotated[list[Line300], Field(max_length=20)]]
    count: Annotated[int, Field(ge=1)] = 1
    steps: Annotated[list[Line300], Field(max_length=8)] = []
    met: bool | None = None

    @model_validator(mode="after")
    def _steps_use_the_known_verbs(self) -> Self:
        problems: list[Problem] = []
        waits = 0
        for index, step in enumerate(self.steps):
            verb = (step.split(None, 1) or [""])[0].lower()
            if verb not in BEHAVIOR_VERBS:
                problems.append((("steps", index), f"step {clip(step, 60)!r} starts with {clip(verb, 30)!r}; allowed: {', '.join(BEHAVIOR_VERBS)}"))
            elif verb == "wait":
                waits += 1
        if waits > MAX_WAITS:
            problems.append((("steps",), f"at most {MAX_WAITS} wait steps per item, this one has {waits}"))
        if problems:
            _raise("ExpectedItem", problems)
        return self


class CheckResult(Value):
    """What running one check once gave. exit_code 0 passes; 1 fails; 97 a pinned test changed; 127 the runner or CLI
    is missing (or the name is unknown). `attempt` is the close run this belongs to (1 to 3)."""

    attempt: Annotated[int, Field(ge=1, le=MAX_ATTEMPTS)]
    exit_code: int
    evidence: Text2000 = ""
    ts: Ts


def _registry_arity_problem(template: str, count: int) -> str | None:
    """Why `count` arguments do not fit one of the 14 registry checks, or None. The registry checks are hard model
    rules (a template that gets this wrong is a bug); the plugin's three are open-time rules instead (`open_rules`)."""
    limits = _ARITY[template]
    if limits[0] <= count <= limits[1]:
        return None
    if template == "reply-valid":
        return f"reply-valid takes exactly 2 args (the reply family and kind), got {count}"
    if template == "answer-recorded":
        return f"answer-recorded takes exactly 1 arg (the question message id), got {count}"
    return f"{template} takes no args, got {count}"


class Check(Value):
    """One declared check. `text` is the plain sentence people read; `relevance` says why the check tests the goal (None =
    not given: `open_atom` fills in a default); `results` has one entry per close run."""

    template: CheckTemplate
    args: Annotated[list[Line500], Field(max_length=8)] = []
    text: Text300 = ""
    expect: Union[bool, int, None] = None
    relevance: Text300 | None = None
    relevance_source: Literal["declared", "default"] = "declared"
    target_sha256: Sha256 | None = None
    results: Annotated[list[CheckResult], Field(max_length=MAX_ATTEMPTS)] = []

    @model_validator(mode="after")
    def _registry_checks_take_their_arguments(self) -> Self:
        if self.template in REGISTRY_CHECKS:
            problem = _registry_arity_problem(self.template, len(self.args))
            if problem:
                raise ValueError(problem)
        return self


class Verify(Value):
    checks: Annotated[list[Check], Field(max_length=12)] = []


class AtomEdge(Value):
    atom: AtomId
    why: Line300


class Refusal(Value):
    """Why an open (or a close, or an abandon) was refused: a short code and a sentence."""

    code: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    message: Reason600


def _refusal(code: str, message: str) -> Refusal:
    return Refusal(code=code, message=clip(message, 600))


def default_relevance(check: Check) -> str:
    """The relevance a check gets when it gives none: a registry check's own sentence (S4-fnodes-02), else the plugin's
    `declared: <template> on <first argument>` (SA:204)."""
    if check.template in REGISTRY_CHECKS:
        return clip(check.text or f"declared: {check.template}", 300)
    return clip(f"declared: {check.template} on {check.args[0] if check.args else '?'}", 300)


def check_sentence(check: Check) -> str:
    """The plain sentence of a check: its `text`, else the plugin's own wording (SA `_verify_sentence`), else its name."""
    if check.text:
        return check.text
    args = check.args
    if check.template == "file-exists" and args:
        return (f"the file {args[0]} exists and is not empty" if len(args) == 1
                else f"the files {', '.join(args)} exist and are not empty")
    if check.template == "grep-count" and len(args) >= 2:
        return f'the text "{args[0]}" appears in {args[1]}'
    if check.template == "named-test" and args:
        return f"the test {args[0]} passes"
    return check.template


class AtomDraft(Value):
    """What the layer declares before the work. A draft is not validated against the plugin's rules: `open_atom` is, and a
    draft that breaks them becomes a stored refused atom."""

    goal: Text600 = ""
    constraints: Annotated[list[Constraint], Field(max_length=20)] = []
    context: Annotated[list[Line200], Field(max_length=40)] = []      # references only (J2:5135)
    work: Work
    model: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None
    effort: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None
    touches: Annotated[list[Line300], Field(max_length=40)] = []
    outputs: Annotated[list[Line300], Field(max_length=40)] = []
    expected: Annotated[list[ExpectedItem], Field(max_length=20)] = []
    verify: Verify = Field(default_factory=Verify)
    depends_on: Annotated[list[AtomEdge], Field(max_length=40)] = []
    supersedes: AtomId | None = None


class OutputItem(Value):
    """What the work produced: `make` gives an artifact, `do` a deed; `form` is an open list (AS:42-55)."""

    verb: Literal["make", "do"]
    name: Line300
    form: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    ref: Line300


REPLY_TEXT_MAX: Final = 4000          # characters of a recorded reply (D157): about 4 KB


class AtomReply(Value):
    """The last reply a function's turn got from the model, as the layer saw it (D157): the reply object printed with two-space
    indents and cut to `REPLY_TEXT_MAX` characters, `clipped` saying it was cut. It sits on the atom beside `produced` (the plain
    words of what the turn made or did) and is what the owner's card shows as "The reply". An atom stored before D157 has none."""

    text: Annotated[str, StringConstraints(max_length=REPLY_TEXT_MAX)]
    clipped: bool = False


ATOM_DETAIL_KEYS: Final = ("selectors", "ids", "section", "anchor", "elements", "scope", "channel", "mode", "sent")      # AS:18-20


# ---- the plugin's open-time rules (V1 to V4, plus the two that need context) ------------------------------------------

def _paths_of(check: Check) -> list[str]:
    """The paths a check tests inside the build: every file-exists argument, the file of a grep-count."""
    if check.template == "file-exists":
        return list(check.args)
    if check.template == "grep-count" and len(check.args) > 1:
        return [check.args[1]]
    return []


def _covered(path: str, entries: Iterable[str]) -> bool:
    """Is `path` inside the envelope? A file entry covers exactly itself; a directory entry (trailing "/") covers only
    paths strictly under it; an entry with ".." covers nothing (SA `_v03_covered`)."""
    if ".." in path:
        return False
    for entry in entries:
        if ".." in entry:
            continue
        if entry.endswith("/"):
            if path.startswith(entry) and len(path) > len(entry):
                return True
        elif path == entry:
            return True
    return False


def _bad_args_text(check: Check) -> str | None:
    template, count = check.template, len(check.args)
    limits = _ARITY[template]
    if limits[0] <= count <= limits[1]:
        if template == "grep-count" and not _DIGITS_RE.fullmatch(check.args[2]):
            return f"grep-count min must be a positive integer, got {clip(check.args[2], 40)!r}"
        return None
    if template == "grep-count":
        return f"grep-count needs exactly 3 args (pattern, file, min), got {count}"
    if template == "named-test":
        return "named-test needs the test script path as its first argument"
    if template == "file-exists":
        return "file-exists needs at least one path"
    return _registry_arity_problem(template, count) or f"{template} takes {limits[0]} to {limits[1]} args, got {count}"


def _open_problems(draft: AtomDraft, other_open: Any, abandoned_ids: Collection[str] | None) -> Iterable[tuple[str, str, tuple[str | int, ...]]]:
    """(code, message, place) for every rule the draft breaks, in the plugin's order (SA:172-248). `other_open` None and
    `abandoned_ids` None mean "not known here": the two rules that need them are skipped."""
    if other_open:
        yield ("atom_still_open", f"atom {getattr(other_open, 'id', other_open)} is still open: close it, or abandon it "
               "with a reason, before opening the next atom", ())
    if not draft.goal:
        yield "goal_missing", "the atom has no goal: state what done looks like", ("goal",)
    elif BANAL_GOAL_RE.fullmatch(draft.goal):
        yield "goal_banal", f"goal is banal ({draft.goal!r}): state the observable outcome", ("goal",)
    checks = draft.verify.checks
    if not checks:
        yield "verify_missing", "the atom declares no check: declare at least one check before the work", ("verify", "checks")
    for index, check in enumerate(checks):
        text = _bad_args_text(check)
        if text:
            yield "bad_args", text, ("verify", "checks", index, "args")
    for index, check in enumerate(checks):
        if check.template == "grep-count" and len(check.args) == 3 and _DIGITS_RE.fullmatch(check.args[2]) and int(check.args[2]) < 1:
            yield ("vacuous_check", "grep-count min=0 is vacuous (n>=0 is always true): declare min >= 1",
                   ("verify", "checks", index, "args"))
    for index, check in enumerate(checks):
        if check.relevance is not None and not check.relevance:
            yield "relevance_empty", "the verifier relevance is empty: state WHY this check tests the goal", ("verify", "checks", index, "relevance")
    for index, check in enumerate(checks):
        if check.template == "named-test" and check.target_sha256 is None:
            yield ("pin_missing", "named-test needs target_sha256: pin the hash of the test file when the atom opens",
                   ("verify", "checks", index, "target_sha256"))
    for index, check in enumerate(checks):
        for path in _paths_of(check):
            if ".." in path:
                yield ("dotdot", f"verify target {clip(path, 80)!r} contains '..': a check may only test files inside the atom's envelope",
                       ("verify", "checks", index, "args"))
    envelope = [*draft.touches, *draft.outputs]
    if envelope:
        for index, check in enumerate(checks):
            for path in _paths_of(check):
                if ".." not in path and not _covered(path, envelope):
                    yield ("outside_envelope", f"verify target {clip(path, 80)!r} is outside the declared touches and outputs: "
                           "the check must test what this atom claims to change", ("verify", "checks", index, "args"))
    if draft.supersedes and abandoned_ids is not None and draft.supersedes not in abandoned_ids:
        yield ("bad_supersedes", f"supersedes target {draft.supersedes} is not an abandoned atom: abandon it with a reason first",
               ("supersedes",))


def open_rules(draft: AtomDraft, other_open: Any = None, abandoned_ids: Collection[str] | None = None) -> Refusal | None:
    """The first plugin rule the draft breaks, as a Refusal, or None. One function backs both the model (which passes
    neither context argument, so `atom_still_open` and `bad_supersedes` are skipped) and `open_atom`. The order is the
    plugin's, and the first rule wins: atom_still_open, goal_missing, goal_banal, verify_missing, bad_args,
    vacuous_check, relevance_empty, pin_missing, dotdot, outside_envelope, bad_supersedes."""
    for code, message, _ in _open_problems(draft, other_open, abandoned_ids):
        return _refusal(code, message)
    return None


# ---- the Atom ------------------------------------------------------------------------------------------------------

def _last_failing(atom: "Atom") -> list[tuple[Check, CheckResult]]:
    """(check, its last result) for each check whose last result is not a pass."""
    return [(check, check.results[-1]) for check in atom.verify.checks if check.results and check.results[-1].exit_code != EXIT_PASS]


@record
class Atom(Record, AtomDraft):
    """A work atom: the draft plus its life. Stored states are open, closed, refused and abandoned; `verify_failed` is
    never stored, it is an atom abandoned with abandon_code "verify_failed" (see `atom_display_state`)."""

    FAMILY = "atom"
    kind: Literal["atom"] = "atom"
    id: AtomId
    node_id: Name60
    department_id: NodeId | None = None
    workflow_id: WorkflowId | None = None
    task_id: Id64 | None = None
    session_id: Id64 | None = None            # the plugin's `sid`; for a function atom, the sid of `atom_sid`
    state: Literal["open", "closed", "refused", "abandoned"] = "open"
    attempt: Annotated[int, Field(ge=0, le=MAX_ATTEMPTS)] = 0
    closed_by: Literal["verify", "manual-override"] | None = None
    reason: Reason600 | None = None
    refusal: Refusal | None = None
    abandon_code: Literal["verify_failed", "run_ended", "replaced", "manual"] | None = None
    produced: Annotated[list[OutputItem], Field(max_length=40)] = []
    notes: Text600 = ""
    reply: AtomReply | None = None            # D157: the last reply of the turn; additive, an atom stored before it has none
    details: JsonObject = {}
    ts_open: Ts
    ts_closed: Ts | None = None

    @model_validator(mode="before")
    @classmethod
    def _abandoned_defaults_to_manual(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("state") == "abandoned" and data.get("abandon_code") is None:
            return {**data, "abandon_code": "manual"}
        return data

    @model_validator(mode="after")
    def _plugin_rules(self) -> Self:
        problems: list[Problem] = []
        if self.state != "refused":                      # a refused atom records what was refused: V1 to V4 do not apply
            problems += [(place, f"{code}: {message}") for code, message, place in _open_problems(self, None, None)]
            for index, check in enumerate(self.verify.checks):
                if not check.relevance:
                    problems.append((("verify", "checks", index, "relevance"), "relevance_empty: a stored check always has a relevance"))
        problems += self._state_problems()
        for index, check in enumerate(self.verify.checks):
            if len(check.results) != self.attempt:
                problems.append((("verify", "checks", index, "results"),
                                 f"a check has one result per attempt: attempt is {self.attempt}, this check has {len(check.results)}"))
            elif any(result.attempt != number for number, result in enumerate(check.results, 1)):
                problems.append((("verify", "checks", index, "results"), "results are numbered 1, 2, 3 in the order the attempts ran"))
        unknown = sorted(set(self.details) - set(ATOM_DETAIL_KEYS))
        if unknown:
            problems.append((("details",), f"details may hold only {', '.join(ATOM_DETAIL_KEYS)}; not {', '.join(clip(k, 30) for k in unknown)}"))
        if problems:
            _raise("Atom", problems)
        return self

    def _state_problems(self) -> list[Problem]:      # V5: what each state requires and forbids
        def need(ok: bool, field: str, text: str) -> list[Problem]:
            return [] if ok else [((field,), text)]
        s = self.state
        out: list[Problem] = []
        if s == "open":
            out += need(self.closed_by is None, "closed_by", "an open atom must not have closed_by")
            out += need(self.ts_closed is None, "ts_closed", "an open atom must not have ts_closed")
            out += need(self.refusal is None, "refusal", "an open atom must not have a refusal")
            out += need(self.reason is None, "reason", "an open atom must not have a reason")
        elif s == "closed":
            out += need(self.closed_by == "verify", "closed_by", "a closed atom must be closed_by verify")
            out += need(self.ts_closed is not None, "ts_closed", "a closed atom must have ts_closed")
            out += need(self.attempt >= 1, "attempt", "a closed atom must have run at least one attempt")
            out += need(self.refusal is None, "refusal", "a closed atom must not have a refusal")
            if not all(check.results and check.results[-1].exit_code == EXIT_PASS for check in self.verify.checks):
                out.append((("verify", "checks"), "a closed atom must have a passing last result on every check"))
        elif s == "abandoned":
            out += need(self.reason is not None, "reason", "an abandoned atom must have a reason")
            out += need(self.closed_by == "manual-override", "closed_by", "an abandoned atom must be closed_by manual-override")
            out += need(self.ts_closed is not None, "ts_closed", "an abandoned atom must have ts_closed")
            out += need(self.refusal is None, "refusal", "an abandoned atom must not have a refusal")
        else:      # refused
            out += need(self.refusal is not None, "refusal", "a refused atom must record its refusal")
            out += need(self.attempt == 0, "attempt", "a refused atom never ran: attempt must be 0")
            out += need(self.ts_closed is not None, "ts_closed", "a refused atom must have ts_closed")
            out += need(self.closed_by is None, "closed_by", "a refused atom must not have closed_by")
            out += need(self.supersedes is None, "supersedes", "a refused atom supersedes nothing (nothing opened)")
        if s != "abandoned":
            out += need(self.abandon_code is None, "abandon_code", "only an abandoned atom may have an abandon_code")
        return out


# ---- lifecycle -------------------------------------------------------------------------------------------------------

class Seen(Value):
    """What the layer saw while the work ran. `work` and `model` correct the declaration; `note` is the layer's own
    trace text and the library stores nothing of it (S4-fnodes-03). Since D157 it also hands over what the turn produced:
    `produced` (the plain words, replacing what the atom held) and `reply` (the last reply the model gave). Nothing else
    about the atom changes."""

    work: Literal["llm", "bash", "manual"] | None = None
    model: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None
    note: Annotated[str, StringConstraints(max_length=200)] = ""
    produced: Annotated[list[OutputItem], Field(max_length=40)] = []
    reply: AtomReply | None = None


CardLabel = Literal["WORK ATOM OPEN", "WORK ATOM CLOSED", "VERIFY FAILED", "WORK ATOM ABANDONED", "ATOM REFUSED"]
CardRowLabel = Literal["Goal", "Done when", "Done by", "Limits", "Using", "Ref", "Result", "Proof", "Output", "Recorded",
                       "Why", "Next", "Reason"]      # the plugin's row names (SA:98-143, HK:60-78)


class CardRow(Value):
    label: CardRowLabel
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class Card(Value):
    """What the owner sees at a transition (the plugin's card). It is built inside the transition and is never optional."""

    label: CardLabel
    goal: Text600 = ""
    rows: Annotated[list[CardRow], Field(max_length=14)] = []


Outcome = Literal["opened", "closed", "verify_failed", "refused", "abandoned"]
_CARD_LABELS: Final = {"opened": "WORK ATOM OPEN", "closed": "WORK ATOM CLOSED", "verify_failed": "VERIFY FAILED",
                       "abandoned": "WORK ATOM ABANDONED", "refused": "ATOM REFUSED"}


class Transition(Value):
    """What one lifecycle step did. `atom` is the atom after the step (unchanged for a refused close or abandon, which
    set `refusal` and publish no event); `events` are the `atom.transitioned` events a store publishes after commit."""

    outcome: Outcome
    atom: Atom
    card: Card
    events: Annotated[list[DomainEvent], Field(max_length=4)] = []
    refusal: Refusal | None = None

    @model_validator(mode="after")
    def _outcome_fits_the_atom(self) -> Self:
        a, out = self.atom, self.outcome
        fits = {"opened": a.state == "open" and a.attempt == 0, "verify_failed": a.state == "open" and a.attempt >= 1,
                "closed": a.state == "closed", "abandoned": a.state == "abandoned", "refused": True}[out]
        problems: list[Problem] = []
        if not fits:
            problems.append((("outcome",), f"outcome {out} does not fit an atom that is {a.state} at attempt {a.attempt}"))
        if (out == "refused") != (self.refusal is not None):
            problems.append((("refusal",), "a refusal is set exactly when the outcome is refused"))
        if self.card.label != _CARD_LABELS[out]:
            problems.append((("card", "label"), f"the card of outcome {out} is {_CARD_LABELS[out]}, not {self.card.label}"))
        if problems:
            _raise("Transition", problems)
        return self


def atom_display_state(atom: Any) -> Literal["open", "verify_failed", "closed", "refused", "abandoned"]:
    """The five words every surface shows (function-nodes.md section 6.2): the stored state, except that an abandoned atom
    whose abandon_code is "verify_failed" shows as verify_failed. An open atom is always open, whatever its attempt.
    Takes an Atom, or a mapping with `state` and `abandon_code` (an event body)."""
    get = atom.get if isinstance(atom, Mapping) else lambda key: getattr(atom, key, None)
    state = get("state")
    if state not in ("open", "closed", "refused", "abandoned"):
        raise AtomError("bad_state", f"an atom state is open, closed, refused or abandoned, not {clip(str(state), 40)!r}")
    return "verify_failed" if state == "abandoned" and get("abandon_code") == "verify_failed" else state


def _row(label: str, text: str | None) -> CardRow | None:
    text = (text or "").strip()
    return CardRow(label=label, text=clip(text, 2000)) if text else None


def _rows(*rows: CardRow | None) -> list[CardRow]:
    return [row for row in rows if row is not None]


def _done_by(atom: Atom) -> str:
    who = {"llm": "an AI call", "skill": "a Sutra skill", "bash": "code, no AI call", "manual": "you"}[atom.work.dispatch_kind]
    return who + (f" ({atom.work.ref})" if atom.work.ref else "") + (f" [model: {atom.model}]" if atom.model else "")


def _failing_evidence(atom: Atom) -> str:
    return "; ".join(f"{check.template}: {result.evidence or 'exit ' + str(result.exit_code)}" for check, result in _last_failing(atom))


def build_card(outcome: Outcome, atom: Atom, refusal: Refusal | None = None) -> Card:
    """The card of a transition, from the outcome and the atom after it (the plugin's four cards plus ATOM REFUSED)."""
    ref = _row("Ref", atom.id)
    if outcome == "opened":
        rows = _rows(_row("Done when", "; ".join(check_sentence(c) for c in atom.verify.checks)), _row("Done by", _done_by(atom)),
                     _row("Limits", "; ".join(c.text for c in atom.constraints)), _row("Using", "; ".join(atom.context)), ref)
    elif outcome == "closed":
        sentences = "; ".join(check_sentence(c) for c in atom.verify.checks)
        outputs = next((arg for c in atom.verify.checks for arg in c.args if "/" in arg), None) or (atom.outputs[0] if atom.outputs else None)
        rows = _rows(_row("Result", "goal reached"),
                     _row("Proof", f"checked {sentences} -- passed" + (f" on attempt {atom.attempt}" if atom.attempt > 1 else "")),
                     _row("Output", outputs), _row("Recorded", "added to the Atom log"), ref)
    elif outcome == "verify_failed":
        more = (f"fix the work, then close again (attempt {atom.attempt + 1} of {MAX_ATTEMPTS})" if atom.attempt < MAX_ATTEMPTS
                else "no tries are left: the atom will be abandoned")
        rows = _rows(_row("Result", f"not done -- attempt {atom.attempt} of {MAX_ATTEMPTS} did not pass, so this stays open"),
                     _row("Why", _failing_evidence(atom) or "the check returned a failure"), _row("Next", more), ref)
    elif outcome == "abandoned":
        why = _row("Why", _failing_evidence(atom) or "no failed check result was recorded") if atom.abandon_code == "verify_failed" else None
        rows = _rows(_row("Result", "stopped without finishing"), _row("Reason", atom.reason), why, _row("Recorded", "added to the Atom log"), ref)
    else:
        rows = _rows(_row("Reason", (refusal or atom.refusal).message if (refusal or atom.refusal) else "refused"))
    return Card(label=_CARD_LABELS[outcome], goal=atom.goal, rows=rows)


def card(transition: Transition) -> Card:
    """The card of a transition, rebuilt from its outcome and atom (it equals `transition.card` by construction)."""
    return build_card(transition.outcome, transition.atom, transition.refusal)


def _event(atom: Atom, outcome: Outcome, now: int) -> DomainEvent:
    return DomainEvent(type="atom.transitioned", subject_id=atom.id, ts=now, data={
        "atom_id": atom.id, "node_id": atom.node_id, "outcome": outcome, "state": atom.state, "display": atom_display_state(atom)})


def _transition(outcome: Outcome, atom: Atom, now: int, *, refusal: Refusal | None = None, publish: bool = True) -> Transition:
    return Transition(outcome=outcome, atom=atom, card=build_card(outcome, atom, refusal),
                      events=[_event(atom, outcome, now)] if publish else [], refusal=refusal)


def _draft_fields(draft: AtomDraft) -> dict[str, Any]:
    return {name: getattr(draft, name) for name in AtomDraft.model_fields}


def open_atom(draft: AtomDraft, *, id: str, node_id: str, now: int, department_id: str | None = None,
              workflow_id: str | None = None, task_id: str | None = None, session_id: str | None = None,
              other_open: Any = None, abandoned_ids: Collection[str] = ()) -> Transition:
    """Declare an atom. It opens (outcome `opened`, a check without relevance gets the default one, no tries yet) or, when
    the draft breaks a plugin rule, it is STORED refused (outcome `refused`, attempt 0, ts_closed = now, the refusal in
    the atom and in the Transition): a refusal is logged, ledgered and carded, never silent (S4-fnodes-05).
    `other_open` is the node's other open atom (or its id), `abandoned_ids` the atoms `supersedes` may name."""
    ids = {"id": id, "node_id": node_id, "department_id": department_id, "workflow_id": workflow_id, "task_id": task_id, "session_id": session_id}
    fresh = [check.evolve(results=[]) for check in draft.verify.checks]      # a freshly opened atom has no tries
    refusal = open_rules(draft, other_open, abandoned_ids)
    if refusal is not None:
        atom = Atom(**{**_draft_fields(draft), "verify": Verify(checks=fresh), "supersedes": None}, **ids, state="refused", attempt=0,
                    refusal=refusal, ts_open=now, ts_closed=now)
        return _transition("refused", atom, now, refusal=refusal)
    given = [c if c.relevance is not None else c.evolve(relevance=default_relevance(c), relevance_source="default") for c in fresh]
    atom = Atom(**{**_draft_fields(draft), "verify": Verify(checks=given)}, **ids, ts_open=now)
    return _transition("opened", atom, now)


def _apply_seen(atom: Atom, seen: Seen | None) -> Atom:
    """S4-fnodes-03: a differing `seen.work` replaces `work.dispatch_kind` and the notes say "declared <old>, did <new>";
    `seen.model` fills an empty `model`. D157: `seen.produced` and `seen.reply`, when given, replace `produced` and `reply`.
    Nothing else changes."""
    if seen is None:
        return atom
    changes: dict[str, Any] = {}
    if seen.work is not None and seen.work != atom.work.dispatch_kind:
        changes["work"] = atom.work.evolve(dispatch_kind=seen.work)
        changes["notes"] = clip(f"{atom.notes} declared {atom.work.dispatch_kind}, did {seen.work}".strip(), 600)
    if seen.model is not None and not atom.model:
        changes["model"] = seen.model
    if seen.produced:                       # D157: what the turn made or did; the newest sight of it replaces the last one
        changes["produced"] = list(seen.produced)
    if seen.reply is not None:
        changes["reply"] = seen.reply
    return atom.evolve(**changes) if changes else atom


def _refused(atom: Atom, code: str, message: str, now: int) -> Transition:
    """A close or abandon the rules refuse: the atom is unchanged, the Transition says why, and nothing is published."""
    return _transition("refused", atom, now, refusal=_refusal(code, message), publish=False)


def _drifted(atom: Atom) -> Refusal | None:
    """The envelope check again at close (SA:292-319). An atom cannot change after open, so this only fires for an atom
    that was not validated (`model_construct`)."""
    envelope = [*atom.touches, *atom.outputs]
    for check in atom.verify.checks:
        for path in _paths_of(check):
            if ".." in path:
                return _refusal("dotdot", f"close refused: verify target {clip(path, 80)!r} contains '..'")
            if envelope and not _covered(path, envelope):
                return _refusal("outside_envelope", f"close refused: verify target {clip(path, 80)!r} left the atom's declared envelope")
    return None


def close_atom(atom: Atom, results: Sequence[CheckResult], now: int, *, pins_now: Mapping[int, str] | None = None,
               seen: Seen | None = None) -> Transition:
    """Run-and-record: `results` holds one CheckResult per check, in order, for attempt `atom.attempt + 1`. A pinned
    named-test whose current hash (`pins_now[check index]`) differs from its pin gets exit 97, whatever the runner said.
    Every result 0 -> `closed` (closed_by verify). Otherwise `verify_failed`: attempt + 1, the results are kept and the
    atom stays open (the layer abandons it when no tries are left). Refused, atom unchanged: not_open,
    attempts_exhausted, bad_results, and envelope drift (outside_envelope, dotdot)."""
    if atom.state != "open":
        return _refused(atom, "not_open", f"atom {atom.id} is {atom.state}, not open", now)
    if atom.attempt >= MAX_ATTEMPTS:
        return _refused(atom, "attempts_exhausted", f"atom {atom.id} used all {MAX_ATTEMPTS} attempts: abandon it with a reason", now)
    number, checks, results = atom.attempt + 1, atom.verify.checks, list(results)
    if len(results) != len(checks):
        return _refused(atom, "bad_results", f"close needs one result per check: {len(checks)} checks, {len(results)} results", now)
    if any(result.attempt != number for result in results):
        return _refused(atom, "bad_results", f"every result of this close belongs to attempt {number}", now)
    drift = _drifted(atom)
    if drift is not None:
        # An atom that breaks its own envelope rule was altered behind the model's back (model_copy skips validation). A
        # Transition validates the atom it holds, so this one refusal is built without validation; nothing is stored from it.
        return Transition.model_construct(outcome="refused", atom=atom, card=build_card("refused", atom, drift), events=[], refusal=drift)
    pins = pins_now or {}
    judged = []
    for index, (check, result) in enumerate(zip(checks, results)):
        now_sha = pins.get(index)
        if check.template == "named-test" and check.target_sha256 is not None and now_sha is not None and now_sha != check.target_sha256:
            result = result.evolve(exit_code=EXIT_PIN_CHANGED, evidence=PIN_EVIDENCE)
        judged.append(check.evolve(results=[*check.results, result]))
    verify = Verify(checks=judged)
    if all(result.exit_code == EXIT_PASS for result in (check.results[-1] for check in judged)):
        after = atom.evolve(verify=verify, attempt=number, state="closed", closed_by="verify", ts_closed=now)
        outcome: Outcome = "closed"
    else:
        after = atom.evolve(verify=verify, attempt=number)
        outcome = "verify_failed"
    return _transition(outcome, _apply_seen(after, seen), now)


def abandon_atom(atom: Atom, reason: str, now: int, *, code: str = "manual", seen: Seen | None = None) -> Transition:
    """End an open atom on purpose, with a reason (recorded, never silent). It runs no check and frees the node. `code` is
    manual (default), verify_failed (the tries are used up and J2 has no recovery), run_ended or replaced."""
    if code not in ("verify_failed", "run_ended", "replaced", "manual"):
        raise AtomError("bad_code", f"an abandon code is verify_failed, run_ended, replaced or manual, not {clip(str(code), 40)!r}")
    reason = (reason or "").strip()
    if not reason:      # the plugin asks for the reason before it looks at the atom (SA:373-391)
        return _refused(atom, "reason_missing", "abandon needs a reason: it is recorded, never silent", now)
    if atom.state != "open":
        return _refused(atom, "not_open", f"atom {atom.id} is {atom.state}, not open", now)
    after = atom.evolve(state="abandoned", reason=clip(reason, 600), closed_by="manual-override", abandon_code=code, ts_closed=now)
    return _transition("abandoned", _apply_seen(after, seen), now)


# ---- the Atom log ----------------------------------------------------------------------------------------------------

class LedgerVerify(Value):
    template: CheckTemplate
    exit_code: int


@record
class LedgerRow(Record):
    """One row of the Atom log: the plugin's `atom-ledger-v0.3` plus node_id and department_id; refused and verify_failed
    rows are declared additions to it (S2-models-10, S4-fnodes-08). One row per atom, written when it ends."""

    FAMILY = "atom_ledger_row"
    kind: Literal["atom_ledger_row"] = "atom_ledger_row"
    atom_id: AtomId
    node_id: Name60
    department_id: NodeId | None = None
    session_id: Id64 | None = None
    goal: Text600 = ""
    status: Literal["closed", "verify_failed", "abandoned", "refused"]
    verify: LedgerVerify | None = None
    attempt: Annotated[int, Field(ge=0, le=MAX_ATTEMPTS)] = 0
    model: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None
    effort: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None
    touches: Annotated[list[Line300], Field(max_length=40)] = []
    relevance: Line300 | None = None
    relevance_source: Literal["declared", "default"] | None = None
    reason: Reason600 | None = None
    ts: Ts

    @model_validator(mode="after")
    def _status_rules(self) -> Self:
        problems: list[Problem] = []
        passed = self.verify is not None and self.verify.exit_code == EXIT_PASS
        if self.status == "closed":
            if not passed:
                problems.append((("verify",), "a closed row has verify with exit_code 0"))
        elif self.status == "verify_failed":
            if self.verify is None or passed:
                problems.append((("verify",), "a verify_failed row has verify with a non-zero exit_code (the last failing check)"))
            if not self.reason:
                problems.append((("reason",), "a verify_failed row has a reason"))
        else:
            if self.verify is not None:
                problems.append((("verify",), f"a {self.status} row has no verify"))
            if not self.reason:
                problems.append((("reason",), f"a {self.status} row has a reason"))
        if problems:
            _raise("LedgerRow", problems)
        return self


def ledger_row(atom: Atom) -> LedgerRow:
    """The Atom log row of an atom that ended: status is its display word (verify_failed comes from abandon_code). A closed
    row shows the first check; a verify_failed row the last check whose last result failed (exit 1 when an atom was
    abandoned as verify_failed with no failed try on record); refused and abandoned rows carry no verify."""
    status = atom_display_state(atom)
    if status == "open":
        raise AtomError("not_terminal", f"atom {atom.id} is still open: only an atom that ended has a ledger row")
    checks = atom.verify.checks
    shown: Check | None = checks[0] if checks else None
    verify: LedgerVerify | None = None
    if status == "closed" and shown is not None:
        verify = LedgerVerify(template=shown.template, exit_code=EXIT_PASS)
    elif status == "verify_failed" and checks:
        failing = _last_failing(atom)
        shown, exit_code = (failing[-1][0], failing[-1][1].exit_code) if failing else (checks[-1], EXIT_FAIL)
        verify = LedgerVerify(template=shown.template, exit_code=exit_code)
    reason = atom.refusal.message if status == "refused" and atom.refusal else atom.reason
    return LedgerRow(
        atom_id=atom.id, node_id=atom.node_id, department_id=atom.department_id, session_id=atom.session_id, goal=atom.goal,
        status=status, verify=verify, attempt=atom.attempt, model=atom.model, effort=atom.effort, touches=atom.touches,
        relevance=(shown.relevance or None) if shown else None, relevance_source=shown.relevance_source if shown and shown.relevance else None,
        reason=reason, ts=atom.ts_closed if atom.ts_closed is not None else atom.ts_open)


# ---- atom/1: J2's view of an atom (j2_schema.py, docs/atom-schema.json) --------------------------------------------------

FINAL_FORMS: Final = ("page", "doc", "send")      # makes that are the deliverable itself; a send is a deed that ends a chain
MAKE_CHECKS: Final = {"file-exists": "exists", "element-count": "exists", "grep-count": "exists", "heading-present": "exists",
                      "section-not-empty": "exists", "facts-present": "meets the defined output", "lld-slice": "meets the defined output"}
DO_CHECKS: Final = ("behavior-steps", "deed-send")      # a do item has one check, "receipt": a receipt exists and shows success


class ViewHow(Value):
    kind: Literal["AI", "code"]
    agent: Annotated[str, StringConstraints(max_length=80)] | None = None
    steps: Text2000 = ""


class ViewCheck(Value):
    check: Literal["exists", "valid", "meets the defined output", "receipt"]
    applies_to: Annotated[str, StringConstraints(max_length=4000)] | None = None
    method: Annotated[str, StringConstraints(min_length=1, max_length=400)]
    met: bool | None = None
    evidence: Text2000 | None = None


class AtomView(Value):
    """The atom/1 document (payload `atom_view` v1): the shape J2's page reads, so the J2 UI is unchanged (D6). `stale` and
    `rechecked` are board/1 additions; `wire()` leaves them out when unset, as J2 does."""

    schema_: Literal["atom/1"] = Field("atom/1", alias="schema")
    id: AtomId
    workflow: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    name: Text300
    owner: Annotated[str, StringConstraints(max_length=80)] | None = None
    status: Literal["open", "closed", "verify_failed", "abandoned"]
    attempt: Annotated[int, Field(ge=0, le=MAX_ATTEMPTS)] | None = None
    goal: Text600 | None = None
    how: ViewHow | None = None
    constraints: Annotated[list[Line300], Field(max_length=20)] = []
    context: Annotated[list[Line200], Field(max_length=40)] = []
    defined_output: Annotated[list[JsonObject], Field(max_length=20)] = []
    verification: Annotated[list[ViewCheck], Field(max_length=36)] = []
    output: Annotated[list[OutputItem], Field(max_length=40)] = []
    depends_on: Annotated[list[AtomEdge], Field(max_length=200)] = []
    used_by: Annotated[list[AtomEdge], Field(max_length=200)] = []
    notes: Text600 = ""
    details: JsonObject = {}
    stale: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None
    rechecked: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None

    def wire(self) -> dict[str, Any]:
        """J2's JSON for this view: the keys of atom/1, with `stale` and `rechecked` only when set."""
        data = self.model_dump(mode="json", by_alias=True)
        for key in ("stale", "rechecked"):
            if data[key] is None:
                del data[key]
        return data


REGISTRY.register_payload("atom_view", 1, AtomView)


def dedupe_edges(edges: Iterable[Any]) -> list[AtomEdge]:
    """The edges with each (atom, why) pair once, in the order they were recorded. Takes AtomEdge objects or J2's dicts."""
    out: list[AtomEdge] = []
    seen: set[tuple[str, str]] = set()
    for item in edges or ():
        edge = item if isinstance(item, AtomEdge) else AtomEdge.model_validate(item)
        if (edge.atom, edge.why) not in seen:
            seen.add((edge.atom, edge.why))
            out.append(edge)
    return out


def _view_status(atom: Atom, workflow: Mapping[str, Any] | None, ended: bool) -> str:
    """j2_schema.atom_status in the library's terms. closed -> closed; abandoned -> abandoned, or verify_failed with that
    abandon_code; refused -> abandoned (the view enum is closed by D6); open -> J2's derivation: a failed last result is
    final when the workflow is known and no longer running, or when three attempts are used; an unfunded workflow, or a
    run that ended on an atom never checked in a workflow that is not done, makes it abandoned; else open."""
    if atom.state == "closed":
        return "closed"
    if atom.state == "refused":
        return "abandoned"
    if atom.state == "abandoned":
        return "verify_failed" if atom.abandon_code == "verify_failed" else "abandoned"
    ws = (workflow or {}).get("status")
    if _last_failing(atom) and ((workflow is not None and ws != "running") or atom.attempt >= MAX_ATTEMPTS):
        return "verify_failed"
    if ws == "unfunded" or (ended and atom.attempt == 0 and ws not in (None, "done")):
        return "abandoned"
    return "open"


def atom_view(atom: Atom, workflow: Mapping[str, Any] | None = None, edges: Iterable[Any] = (), ended: bool = False, *,
              stale: str | None = None, rechecked: str | None = None) -> AtomView:
    """The atom/1 view of an atom (a port of j2_schema.atom_view). `workflow` is a mapping with `name` and `status` (so this
    module never imports the workflow module); `edges` are the atoms this one depends on, besides its own `depends_on`;
    `ended` says the run is over; `stale` and `rechecked` are the board/1 question ids (the Atom does not keep them).
    `used_by` stays empty until `link_views`. One verification row per CheckResult, every attempt, oldest first. A
    refused atom shows as abandoned with `details.refusal`."""
    wf = workflow or {}
    produced = list(atom.produced)
    make_names = [o for o in produced if o.verb == "make"]
    name = (wf.get("name") or (make_names[0].name if make_names else "") or atom.id)
    section_ref = next((o.name for o in make_names if o.form in FINAL_FORMS and "#" in o.ref), None)
    rows: list[ViewCheck] = []
    for number in range(1, atom.attempt + 1):
        for check in atom.verify.checks:
            if len(check.results) < number:
                continue
            result = check.results[number - 1]
            do = check.template in DO_CHECKS
            applies_to = check.text if do else (section_ref or (make_names[0].name if make_names else None) or ", ".join(check.args) or None)
            applies_to = clip(applies_to, 4000) if applies_to else None
            rows.append(ViewCheck(check="receipt" if do else MAKE_CHECKS.get(check.template, "valid"), applies_to=applies_to,
                                  method=f"{check.template}: {check.text}", met=result.exit_code == EXIT_PASS,
                                  evidence=f"{atom.id}:{result.attempt}" if do else result.evidence))
    details = dict(atom.details)
    if atom.state == "refused" and atom.refusal is not None:
        details["refusal"] = {"code": atom.refusal.code, "message": atom.refusal.message}
    return AtomView(
        id=atom.id, workflow=atom.workflow_id or atom.id.split(".")[0], name=clip(str(name), 300), owner=atom.work.agent,
        status=_view_status(atom, workflow, ended), attempt=atom.attempt or None, goal=atom.goal or None,
        how=ViewHow(kind=atom.work.how_kind, agent=atom.work.agent, steps=atom.work.steps),
        constraints=[c.text for c in atom.constraints], context=list(atom.context),
        defined_output=[item.model_dump(mode="json", exclude_defaults=True) for item in atom.expected],
        verification=rows, output=produced, depends_on=dedupe_edges([*atom.depends_on, *(edges or ())]), used_by=[],
        notes=atom.notes, details=details, stale=stale or None, rechecked=rechecked or None)


def atom_kind(view: AtomView) -> Literal["make", "do", "mixed"]:
    """make, do or mixed, derived from the output items (never stored)."""
    verbs = {o.verb for o in view.output}
    return "mixed" if verbs >= {"make", "do"} else "do" if "do" in verbs else "make"


def link_views(views: Sequence[AtomView]) -> list[AtomView]:
    """The views with `used_by` set to the exact inverse of `depends_on` (built here, never by an agent). New objects."""
    known = {v.id for v in views}
    used: dict[str, list[AtomEdge]] = {v.id: [] for v in views}
    for v in views:
        for edge in v.depends_on:
            if edge.atom in known:
                used[edge.atom].append(AtomEdge(atom=v.id, why=edge.why))
    return [v.evolve(used_by=dedupe_edges(used[v.id])) for v in views]


def dependency_edges(workflow: Mapping[str, Any], workflows: Sequence[Mapping[str, Any]]) -> list[AtomEdge]:
    """Edges from a workflow's declared dependencies (proposal ids), for a builder that was given the whole page and nothing
    can be attributed. Dependencies that name no workflow produce nothing."""
    by_proposal = {w.get("proposal_id"): w for w in workflows}
    return [AtomEdge(atom=a.id, why=clip(f"its workflow depends on {by_proposal[d].get('name')}", 300))
            for d in workflow.get("dependencies") or []
            if d in by_proposal and by_proposal[d] is not workflow for a in by_proposal[d].get("atoms") or []]


def run_views(workflows: Sequence[Mapping[str, Any]], given: Mapping[str, Mapping[str, Any]] | None = None,
              ended: bool = False) -> tuple[list[AtomView], list[str]]:
    """(views, warnings) for a run. Each workflow is a mapping with `id`, `name`, `status`, `proposal_id`, `dependencies`
    and `atoms` (a list of Atom). `given` is {workflow id: {"edges": [...], "whole": bool}}, what each builder's prompt
    held. Without a record, or with the whole page given and no attributable edge, edges come from workflow
    dependencies, else stay empty."""
    given = given or {}
    views: list[AtomView] = []
    for w in workflows:
        g = given.get(w["id"]) or {}
        edges = list(g.get("edges") or (dependency_edges(w, workflows) if g.get("whole", True) else []))
        for atom in w.get("atoms") or []:
            views.append(atom_view(atom, w, [e for e in edges if (e.atom if isinstance(e, AtomEdge) else e.get("atom")) != atom.id], ended))
    linked = link_views(views)
    return linked, validate_views(linked)


def validate_atom(view: AtomView, known: Collection[str] | None = None) -> list[str]:
    """Warnings for one view: an edge to an atom that is not in `known` (when given). A missing output verb cannot occur:
    the closed model refuses it."""
    if known is None:
        return []
    return [f"{view.id}: depends on {e.atom}, which is not an atom of this run" for e in view.depends_on if e.atom not in known]


def validate_views(views: Sequence[AtomView]) -> list[str]:
    """Warnings for a run (never change an outcome, a prompt or a retry): dangling edges, cycles, outputs never used that
    are not final outputs, and an informational note for each mixed atom."""
    known = {v.id for v in views}
    out = [w for v in views for w in validate_atom(v, known)]
    by = {v.id: v for v in views}
    state: dict[str, int] = {}
    stack: list[str] = []

    def walk(atom_id: str) -> None:
        state[atom_id] = 1
        stack.append(atom_id)
        for edge in by[atom_id].depends_on:
            if edge.atom not in by:
                continue
            if state.get(edge.atom) == 1:
                out.append("cycle: " + " -> ".join([*stack[stack.index(edge.atom):], edge.atom]))
            elif edge.atom not in state:
                walk(edge.atom)
        stack.pop()
        state[atom_id] = 2

    for atom_id in by:
        if atom_id not in state:
            walk(atom_id)
    out += [f"{v.id}: its output is never used and is not a final output" for v in views
            if v.output and not v.used_by and not any(o.form in FINAL_FORMS for o in v.output)]
    out += [f"info: {v.id} is a mixed atom ({sum(o.verb == 'make' for o in v.output)} make, {sum(o.verb == 'do' for o in v.output)} do)"
            for v in views if atom_kind(v) == "mixed"]
    return out


def ledger_row_from_view(view: AtomView, node_id: str, department_id: str | None, *, now: int = 0) -> LedgerRow:
    """The Atom log row of a builder atom (J2 atom/1) that ended, for the first time its view is terminal (closed,
    verify_failed or abandoned). verify = the check type before ":" in the first verification method, exit 0 for closed
    and 1 for verify_failed; attempt = the view's or 0; model, effort and touches stay empty; the reason comes from the
    view's details (`reason`, or the refusal message) or its notes, else a sentence for the status (for verify_failed the
    evidence of the first unmet check); ts = `now`."""
    if view.status == "open":
        raise AtomError("not_terminal", f"atom {view.id} is still open: only an atom that ended has a ledger row")
    verify = None
    if view.status in ("closed", "verify_failed"):
        method = view.verification[0].method if view.verification else ""
        verify = {"template": method.split(":", 1)[0].strip(), "exit_code": EXIT_PASS if view.status == "closed" else EXIT_FAIL}
    reason = None
    if view.status != "closed":
        refusal = view.details.get("refusal")
        candidates = [view.details.get("reason"), refusal.get("message") if isinstance(refusal, Mapping) else None, view.notes]
        reason = next((c.strip() for c in candidates if isinstance(c, str) and c.strip()), None)
        if reason is None and view.status == "verify_failed":
            unmet = next((row.evidence for row in view.verification if row.met is False and row.evidence), None)
            reason = f"verify failed: {unmet}" if unmet else "verify failed"
        elif reason is None:
            reason = "abandoned: the run ended before this atom was built"
    return LedgerRow(atom_id=view.id, node_id=node_id, department_id=department_id, goal=view.goal or "", status=view.status,
                     verify=verify, attempt=view.attempt or 0, reason=clip(reason, 600) if reason else None, ts=now)
