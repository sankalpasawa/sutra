"""The J2 record catalogue and `gate_record` (library design section 10, flow F6, decision D47; work package L8).

J2 writes its run files itself (D5): `J2Run.save(name, data)` and `post()` keep J2's formatting. The engine hands each file
and each chat line to `gate_record(name, data)` through the `record_saved` hook (patch P8, `engine/hooks.py`), after J2's own
write. The catalogue says which library family a file is checked as; the gate validates and the canonical text is discarded.

    gate_record(name, data, *, mode=None)    the engine's validator; mode `log` (default) or `strict` (`SUTRA_RECORDS`)
    check_record(name, data)                 the same check without a mode: Checked documents, or RecordRejected
    RECORD_FAMILIES                          file pattern => family (what each file is checked as)
    UNCHECKED                                files J2 writes that are deliberately not checked, with the reason
    RecordRejected                           strict mode's error; `fatal = True` and the name is the one P8 stops a run on

`log` mode: a rejection becomes a list of warning strings, which the engine's `EventHooks` writes as `record.warning` trace
lines (this is the `record_rejected` event) and J2's write goes on; the run is never touched. `strict` mode: `RecordRejected`,
and a file that is neither in the catalogue nor in `UNCHECKED` is rejected too.

Files that have a closed model elsewhere in the library are checked as that model. The rest are small payloads registered
HERE (`receipt`, `call_log`, `condition_result`, `artifact_data`, `chain_row`, `run_file.object`, `run_file.list`): they have no
other home, and the catalogue is the only reader. `run_file.*` is bounded open JSON, for the J2 files whose keys no
package has modelled yet (documents.json, sections.json, stage-*.json, report.json, change.json).

Importing this module imports the whole library, so the registry is complete when the engine process (which imports only
this module) starts checking.
"""
import json
import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Final, Literal, Optional

from pydantic import Field, JsonValue, StringConstraints, ValidationError, model_validator
from pydantic_core import InitErrorDetails

from . import (  # noqa: F401  (imported for what they register)
    artifacts, atom, chat, department, evaluation, functions, goal, node, org_chart, templates, wire, workflow,
)
from .base import Value
from .evaluation import ConditionResult
from .gate import GATE, Checked, GateError
from .registry import REGISTRY, RegistryError
from .types import AtomId, JsonObject, Violation, clip, violation, violations_from_validation_error
from .workflow import registered_from_j2

__all__ = [
    "RECORD_MODES", "RECORD_FAMILIES", "UNCHECKED", "RecordRejected", "Route", "route_for", "check_record", "gate_record",
    "record_mode", "Receipt", "CallLog", "ArtifactData", "ChainRow", "RunObject", "RunList",
]

log = logging.getLogger("sutra.library")

RECORD_MODES: Final = ("log", "strict")
MAX_WARNINGS_SHOWN: Final = 3        # violations a log-mode warning names; the rest is counted
ARTIFACT_SCHEMA: Final = "artifact-schema/1"    # the "schema" key of <kind>.json (J2 j2_artifact_models.SCHEMA)
MAX_LIST: Final = 5000               # rows of a list file (workflows, audits, conflicts, conditions, chain, change)

Text = Annotated[str, StringConstraints(max_length=100_000)]
Line = Annotated[str, StringConstraints(max_length=2_000)]
Short = Annotated[str, StringConstraints(max_length=200)]
Big = Annotated[str, StringConstraints(max_length=500_000)]          # a prompt or a raw reply in calls.jsonl


# ============================================ payloads that only the catalogue reads ==========================================

class RunObject(Value):
    """A J2 run file that is one JSON object whose keys no package has modelled: bounded open JSON (500 keys, 32 levels,
    finite numbers). `content` is the file."""

    content: JsonObject


class RunList(Value):
    """A J2 run file that is a list of JSON objects: the same bounds for each row."""

    content: Annotated[list[JsonObject], Field(max_length=MAX_LIST)]


class ChainRow(Value):
    """One row of chain.json: requirement -> HLD component -> LLD section -> built atoms (J2 `_chain_record`; None when a link
    is missing)."""

    requirement: Optional[Short] = None
    component: Optional[Short] = None
    lld_section: Optional[Short] = None
    atoms: Annotated[list[AtomId], Field(max_length=500)] = []


class Receipt(Value):
    """One line of receipts.jsonl, written by code only (J2 `_receipt`, `_expected_receipts`; `[U]` beyond the golden runs).
    Two shapes share the file: a CHECK receipt (`check`, `type`, `expect`, `actual`, `pass`, `evidence`) and an OUTPUT
    receipt (`expected`, `kind`, `met`, `checks`). The keys after `by` are the ones a template routing adds. J2's send record
    (`type: deed-send-record`) is not a Receipt: the catalogue checks it as bounded open JSON."""

    atom: AtomId
    attempt: Annotated[int, Field(ge=0, le=99)]
    of: Annotated[int, Field(ge=1, le=99)]
    t: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    by: Literal["code"]
    target: Optional[Line] = None
    # check receipt
    check: Optional[Line] = None
    type: Optional[Annotated[str, StringConstraints(min_length=1, max_length=40)]] = None
    expect: JsonValue = None
    actual: JsonValue = None
    passed: Optional[bool] = Field(default=None, alias="pass")
    evidence: Optional[Text] = None
    # output receipt
    expected: Optional[Line] = None
    kind: Optional[Annotated[str, StringConstraints(max_length=40)]] = None
    met: Optional[bool] = None
    checks: Optional[Annotated[list[Optional[Line]], Field(max_length=200)]] = None
    # added by a template routing
    template: Optional[Annotated[str, StringConstraints(max_length=200)]] = None
    template_version: Optional[Annotated[int, Field(ge=1, le=999_999)]] = None
    template_route: Optional[JsonObject] = None
    rules: Optional[Annotated[list[JsonObject], Field(max_length=200)]] = None

    @model_validator(mode="after")
    def _one_shape(self) -> "Receipt":
        # judged by value, not by the keys that were sent: the gate checks that the canonical JSON (which holds every key)
        # reads back as the same model
        check = self.evidence is not None
        output = self.checks is not None
        if check == output:
            raise ValueError("a receipt is a check receipt (check, type, pass, evidence) or an output receipt "
                             "(expected, kind, met, checks), not both and not neither")
        if check and (self.expected, self.kind, self.met) != (None, None, None):
            raise ValueError("a check receipt may not carry expected, kind or met")
        if output and (self.check, self.type, self.passed) != (None, None, None):
            raise ValueError("an output receipt may not carry check, type or pass")
        return self


class CallLog(Value):
    """One line of calls.jsonl: J2's `rec` of `_log_call` plus the three texts of the call (`system`, `prompt`, `raw`).
    `usd`, `model` and `provider` are None in mock mode; `atom` and `artifact_schema` appear on some calls only."""

    id: Annotated[int, Field(ge=0)]
    fn: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    step: Annotated[int, Field(ge=0, le=99)]
    cycle: Annotated[int, Field(ge=0, le=9999)]
    t: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    seconds: Annotated[float, Field(ge=0)]
    model: Optional[Short] = None
    provider: Optional[Short] = None
    usd: Optional[Annotated[float, Field(ge=0)]] = None
    tokens: Optional[JsonObject] = None
    chars: JsonObject
    inputs: Annotated[list[JsonValue], Field(max_length=200)] = []
    reply: Optional[JsonObject] = None
    reason: Optional[Text] = None
    atom: Optional[Short] = None
    artifact_schema: Optional[JsonObject] = None
    system: Big = ""
    prompt: Big = ""
    raw: Big = ""


def _problems(title: str, found: list[tuple[tuple[str | int, ...], str]]) -> ValidationError:
    return ValidationError.from_exception_data(title, [
        InitErrorDetails(type="value_error", loc=loc, input=None, ctx={"error": ValueError(text)}) for loc, text in found])


class ArtifactData(Value):
    """<kind>.json and site/<kind>-vN.json: the data beside a document, written by code from what the builders sent
    (J2 `_save_artifact_data`). `schema` is checked and not stored (a field of that name would need an alias that is not a
    Python keyword, design rule 7); `to_json()` puts it back. Each section is checked as the library model of that section."""

    template: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    artifact: Literal["prd", "hld", "lld", "design", "website"]
    version: Annotated[int, Field(ge=1, le=999_999)]
    sections: Annotated[dict[Annotated[str, StringConstraints(min_length=1, max_length=80)], JsonObject], Field(max_length=40)]

    @model_validator(mode="before")
    @classmethod
    def _schema_key(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "schema" in data:
            if data["schema"] != ARTIFACT_SCHEMA:
                raise ValueError(f"schema must be {ARTIFACT_SCHEMA!r}, not {data['schema']!r}")
            data = {k: v for k, v in data.items() if k != "schema"}
        return data

    @model_validator(mode="after")
    def _sections_follow_their_models(self) -> "ArtifactData":
        found: list[tuple[tuple[str | int, ...], str]] = []
        known = artifacts.SECTION_MODELS[self.artifact]
        for name, data in self.sections.items():
            model = known.get(name)
            if model is None:
                found.append((("sections", name), f"{name!r} is not a section of a {self.artifact} (it has {', '.join(known)})"))
                continue
            # a specialised template adds fields of its own (J2_TEMPLATE_LIBRARY=1): the generic model judges the generic
            # fields only, as J2's own `j2_template_lib.validate` does
            own = {(f.alias or n) for n, f in model.model_fields.items()}
            try:
                model.model_validate_json(json.dumps({k: v for k, v in data.items() if k in own}, ensure_ascii=False))
            except ValidationError as exc:
                for err in exc.errors(include_url=False, include_input=False):
                    found.append((("sections", name, *err["loc"]), str(err["msg"])))
        if found:
            raise _problems("ArtifactData", found)
        return self

    def to_json(self) -> dict[str, Any]:
        return {"schema": ARTIFACT_SCHEMA, **self.model_dump(by_alias=True, mode="json")}


for _name, _cls in (("condition_result", ConditionResult), ("run_file.object", RunObject), ("run_file.list", RunList),
                    ("chain_row", ChainRow), ("receipt", Receipt), ("call_log", CallLog), ("artifact_data", ArtifactData)):
    REGISTRY.register_payload(_name, 1, _cls)


# ============================================ the catalogue ====================================================================

class RecordRejected(Exception):
    """Strict mode: J2 wrote a record the library refuses (or one the catalogue does not know). `fatal = True`, and the name is
    the one patch P8 stops a run on (`engine.hooks.is_fatal`). `violations` say what is wrong, with paths inside the record
    (a list file names the row first: `3.results.0.id`)."""

    fatal = True

    def __init__(self, name: str, violations: list[Violation]) -> None:
        self.name = name
        self.violations = list(violations)
        first = self.violations[0] if self.violations else None
        summary = f"{first.path or '<record>'}: {first.message}" if first else "no detail"
        more = f" (+{len(self.violations) - 1} more)" if len(self.violations) > 1 else ""
        super().__init__(f"{name} refused: {summary}{more}")


Prepared = list[tuple[str, Any]]            # (family, payload) pairs to run through GATE.check, in file order


def _rows(data: Any) -> list[Any]:
    if not isinstance(data, list):
        raise _Refused("not_a_list", "this file must be a JSON list")
    return data


class _Refused(Exception):
    def __init__(self, code: str, message: str, path: str = "") -> None:
        super().__init__(message)
        self.code, self.message, self.path = code, message, path


def _object(data: Any) -> Mapping:
    if not isinstance(data, Mapping):
        raise _Refused("not_an_object", "this file must be a JSON object")
    return data


def _p_one(family: str) -> Callable[[str, Any], Prepared]:
    return lambda name, data: [(family, _object(data))]


def _p_goal(name: str, data: Any) -> Prepared:
    d = _object(data)
    return [("goal", {**d, "kind": goal.goal_kind(d)})]


def _p_workflows(name: str, data: Any) -> Prepared:
    out: Prepared = []
    for index, row in enumerate(_rows(data)):
        try:
            out.append(("workflow", registered_from_j2(row)))
        except ValidationError as exc:
            raise _Refused("shape", "; ".join(f"{v.path}: {v.message}" for v in violations_from_validation_error(exc)[:3]),
                           str(index)) from exc
        except workflow.WorkflowError as exc:
            raise _Refused("shape", str(exc), str(index)) from exc
    return out


def _p_atoms(name: str, data: Any) -> Prepared:
    d = _object(data)
    if d.get("schema") != "atom/1":
        raise _Refused("schema", "schema must be 'atom/1'", "schema")
    extra = sorted(set(d) - {"schema", "atoms", "warnings"})
    if extra:
        raise _Refused("extra_forbidden", f"unexpected keys: {', '.join(extra)}")
    warnings_ = d.get("warnings", [])
    if not isinstance(warnings_, list) or not all(isinstance(w, str) and len(w) <= 5000 for w in warnings_) or len(warnings_) > 500:
        raise _Refused("shape", "warnings must be a list of at most 500 strings", "warnings")
    return [("atom_view", a) for a in _rows(d.get("atoms", []))]


def _p_audits(name: str, data: Any) -> Prepared:
    return [("evaluation", {**row, "kind": "recheck" if "trigger" in row else "result"}) if isinstance(row, Mapping)
            else ("evaluation", row) for row in _rows(data)]


def _p_each(family: str, **extra: Any) -> Callable[[str, Any], Prepared]:
    return lambda name, data: [(family, {**row, **extra} if isinstance(row, Mapping) else row) for row in _rows(data)]


def _p_run_list(name: str, data: Any) -> Prepared:
    return [("run_file.list", {"content": _rows(data)})]


def _p_run_object(name: str, data: Any) -> Prepared:
    return [("run_file.object", {"content": _object(data)})]


def _p_lines(family: str, **extra: Any) -> Callable[[str, Any], Prepared]:
    return lambda name, data: [(family, {**_object(data), **extra})]


def _p_receipt(name: str, data: Any) -> Prepared:
    d = _object(data)
    return _p_run_object(name, d) if d.get("type") == "deed-send-record" else [("receipt", d)]


def _p_chat(name: str, data: Any) -> Prepared:
    d = _object(data)
    return _p_run_object(name, d) if d.get("meta") is True else [("run_message", d)]       # the first line is the run header


def _p_templates_file(name: str, data: Any) -> Prepared:
    """templates.json. A decision's `saved` (J2 33aeeda) is where the run keeps its copy of the template: it must be the folder
    `run_tpl_rel` gives for that decision, so a path cannot point at another template's copy."""
    d = _object(data)
    for index, row in enumerate(d.get("decisions") or []):
        if isinstance(row, Mapping) and row.get("saved") is not None and isinstance(row.get("version"), int):
            try:
                want = templates.run_tpl_rel(row)
            except (KeyError, TypeError):
                continue                     # a decision without the keys of a path: the model reports it
            if row["saved"] != want:
                raise _Refused("saved_mismatch", f"saved is {clip(str(row['saved']), 120)!r}, this decision's copy is {want!r}",
                               f"decisions.{index}.saved")
    return [("template.file", d)]


def _p_template_spec(name: str, data: Any) -> Prepared:
    return [("template", _object(data))]


@dataclass(frozen=True)
class Route:
    """How one family of file names is checked. `label` is the pattern as shown in the catalogue, `family` what the file is
    checked as (a registry family, or `family:kind` / `[family]` for a list file)."""

    label: str
    pattern: re.Pattern
    family: str
    prepare: Callable[[str, Any], Prepared]
    rows: bool = False            # a list file (or an envelope of documents): `gate_record` returns None, paths name the row


def _r(label: str, regex: str, family: str, prepare: Callable[[str, Any], Prepared], rows: bool = False) -> Route:
    return Route(label, re.compile(regex), family, prepare, rows)


_TPL = r"templates/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+@v[0-9]+"        # a run's copy of one template version (J2 33aeeda)

ROUTES: Final[tuple[Route, ...]] = (
    _r("goal.json, goal.v<N>.json", r"goal(\.v[0-9]+)?\.json", "goal", _p_goal),
    _r("workflows.json", r"workflows\.json", "workflow:registered (rows)", _p_workflows, rows=True),
    _r("atoms.json", r"atoms\.json", "atom_view (atoms)", _p_atoms, rows=True),
    _r("audits.json", r"audits\.json", "evaluation:result|recheck (rows)", _p_audits, rows=True),
    _r("conflicts.json", r"conflicts\.json", "conflict (rows)", _p_each("conflict"), rows=True),
    _r("conditions*.json", r"conditions(-[a-z0-9]+)?\.json", "condition_result (rows)", _p_each("condition_result"), rows=True),
    _r("style.json", r"style\.json", "artifact.design.style-guide", _p_one("artifact.design.style-guide")),
    _r("memory/lessons.jsonl", r"(memory/)?lessons\.jsonl", "lesson", _p_lines("lesson", kind="lesson")),
    _r("receipts.jsonl", r"receipts\.jsonl", "receipt", _p_receipt),
    _r("chat.jsonl", r"chat\.jsonl", "run_message", _p_chat),
    _r("calls.jsonl", r"calls\.jsonl", "call_log", _p_lines("call_log")),
    _r("templates.json", r"templates\.json", "template.file", _p_templates_file),
    _r("templates/<artifact>/<section>/<slug>@v<N>/spec.json", _TPL + r"/spec\.json", "template", _p_template_spec),
    _r("templates/<artifact>/<section>/<slug>@v<N>/meta.json", _TPL + r"/meta\.json", "template.meta", _p_one("template.meta")),
    _r("templates/<artifact>/<section>/<slug>@v<N>/schema.json", _TPL + r"/schema\.json", "run_file.object", _p_run_object),
    _r("<prd|hld|lld|design|website>.json, site/<kind>-v<N>.json", r"(site/)?(prd|hld|lld|design|website)(-v[0-9]+)?\.json",
       "artifact_data", _p_one("artifact_data")),
    _r("chain.json", r"chain\.json", "chain_row (rows)", _p_each("chain_row"), rows=True),
    _r("documents.json", r"documents\.json", "run_file.object", _p_run_object),
    _r("sections.json", r"sections\.json", "run_file.object", _p_run_object),
    _r("stage-<kind>.json", r"stage-[a-z]+\.json", "run_file.object", _p_run_object),
    _r("report.json", r"report\.json", "run_file.object", _p_run_object),
    _r("change.json", r"change\.json", "run_file.list", _p_run_list),
    _r("settings.json", r"settings\.json", "run_file.object", _p_run_object),      # Decide for me (J2 sync 4): {"decide_for_me": bool}
    *(_r(file, re.escape(file), family, _p_one(family)) for file, family in wire.WIRE_FILES.items()),
)

# file => family, the catalogue as library design section 10 shows it
RECORD_FAMILIES: Final[dict[str, str]] = {r.label: r.family for r in ROUTES}

# Files J2 writes that no closed model covers and the catalogue does not check. `gate_record` accepts them in both modes.
UNCHECKED: Final[tuple[tuple[re.Pattern, str], ...]] = tuple((re.compile(p), why) for p, why in (
    (r"outputs\.jsonl", "J2's workflow outputs: appended by code outside save(); no model yet"),
    (r"template_calls\.jsonl", "the template generator's calls: appended by code outside save(); no model yet"),
    (r"board\.jsonl", "the board's event log: appended by code outside save(); board.json is the checked document"),
    (_TPL + r"/model\.py", "Python source generated from spec.json, not a record"),
    (r"([A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(md|docx|html|png|txt)", "a rendered document or a screenshot, not a record"),
))


def _normal(name: Any) -> str:
    text = str(name or "").replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def route_for(name: str) -> Optional[Route]:
    """The catalogue entry for a file name (a bare name, or a path inside the run folder with forward slashes), or None."""
    text = _normal(name)
    if text.startswith("/") or ".." in text.split("/"):
        return None
    return next((r for r in ROUTES if r.pattern.fullmatch(text)), None)


def is_unchecked(name: str) -> bool:
    text = _normal(name)
    return any(p.fullmatch(text) for p, _ in UNCHECKED)


def record_mode(mode: Optional[str] = None) -> str:
    """`mode`, else SUTRA_RECORDS, else `log`. Anything else is a wiring mistake (`RegistryError` bad_mode)."""
    chosen = (mode if mode is not None else os.environ.get("SUTRA_RECORDS") or "log").strip().lower()
    if chosen not in RECORD_MODES:
        raise RegistryError("bad_mode", f"SUTRA_RECORDS must be one of {', '.join(RECORD_MODES)}, not {chosen!r}")
    return chosen


def _plain(data: Any) -> Any:
    """What J2 wrote: the data after one JSON round trip (tuples become lists, non-string keys strings). NaN, infinity and
    types JSON lacks are refused, since J2's file would not be valid JSON for the page."""
    return json.loads(json.dumps(data, ensure_ascii=False, allow_nan=False))


def check_record(name: str, data: Any) -> Optional[list[Checked]]:
    """Check one record of a J2 run folder against its family. Returns None when the name is not in the catalogue (or is in
    `UNCHECKED`), else one `Checked` per document the file holds (a list file: one per row). Raises `RecordRejected`, whose
    violations carry the row number first. Stores nothing; the canonical text is not J2's formatting and is dropped."""
    route = route_for(name)
    if route is None:
        return None
    try:
        prepared = route.prepare(_normal(name), _plain(data))
    except (TypeError, ValueError, RecursionError) as exc:
        raise RecordRejected(name, [violation("", "not_json", f"not JSON-serialisable: {exc}")]) from exc
    except _Refused as exc:
        raise RecordRejected(name, [violation(exc.path, exc.code, exc.message)]) from exc
    found: list[Violation] = []
    done: list[Checked] = []
    many = route.rows or len(prepared) > 1
    for index, (family, payload) in enumerate(prepared):
        try:
            done.append(GATE.check(family, payload))
        except GateError as exc:
            for v in exc.violations:
                path = f"{index}.{v.path}" if many and v.path else (str(index) if many else v.path)
                found.append(violation(path, v.code, v.message))
        if len(found) >= 50:
            break
    if found:
        raise RecordRejected(name, found[:50])
    return done


def _warnings(rejected: RecordRejected) -> list[str]:
    shown = rejected.violations[:MAX_WARNINGS_SHOWN]
    out = [f"record_rejected {rejected.name}: {(v.path + ': ') if v.path else ''}{v.message}" for v in shown]
    if len(rejected.violations) > len(shown):
        out.append(f"record_rejected {rejected.name}: {len(rejected.violations) - len(shown)} more violations")
    return out


def gate_record(name: str, data: Any, *, mode: Optional[str] = None) -> Checked | list[str] | None:
    """The engine's `record_saved` validator (D47). Returns the `Checked` document of a file that is one document and passed,
    None for a list file that passed or a file the catalogue leaves alone, and in `log` mode a rejection returns the list of
    warning strings (the `record_rejected` event; the engine writes them to its trace and J2's write goes on). In `strict`
    mode a rejection raises `RecordRejected`, and so does a file that is not in the catalogue."""
    chosen = record_mode(mode)
    try:
        checked = check_record(name, data)
    except RecordRejected as rejected:
        if chosen == "strict":
            raise
        warnings = _warnings(rejected)
        for line in warnings:
            log.warning("%s", line)
        return warnings
    if checked is None:
        if chosen == "strict" and not is_unchecked(name):
            raise RecordRejected(str(name), [violation("", "unknown_file", f"{clip(str(name), 120)} is not in the record catalogue")])
        return None
    return checked[0] if len(checked) == 1 and not route_for(name).rows else None
