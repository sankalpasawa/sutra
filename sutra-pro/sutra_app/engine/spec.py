"""What the engine reads before a run: the task and the settings (engine design 4.4, S1-contracts-01, -03).

`TaskSpec` is the engine's view of the orchestrator's `task.json` ("run-spec/1"). The orchestrator's `RunSpec` is the strict
writer and this class the tolerant reader (`extra="ignore"`): two classes of one document, kept in step by a contract test.

`EngineSettings` holds every J2 flag with J2's default (D18). The host resolves them in this order, later wins:

    defaults  <  data/engine.json  <  J2_* in the process environment (dev and tests)  <  data/departments/<id>/engine.json
              <  the task's settings (the keys `TASK_SETTING_KEYS`; the orchestrator validates them)

writes the result to `<run>/settings.json`, exports `to_env()` before it imports J2, and never reads the layers again.
The files hold field names (`{"board": true}`); the environment and the task hold J2's variable names (`J2_BOARD=1`).

Two of the task keys are not settings (`J2_RUN_TEMPLATE`, `J2_RUN_TEMPLATE_WORKFLOWS`, D182): they say which run template this one request starts from,
the host reads them from the task itself and `layered()` ignores them, so they cannot reach J2's environment. `EngineSettings.effective()` computes the
flags that J2 implies from others once (D178). `J2_PUSH_RUNS` and `J2_RUN_BY` are not fields at all: `DataPaths.j2_env()` fixes them (D177).
"""
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Optional, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, field_validator, model_validator

__all__ = [
    "DEPT_ID_RE", "RUN_ID_RE", "SETTING_KEY_RE", "TASK_SCHEMA", "TASK_SETTING_KEYS", "CONNECTORS", "is_dept_id",
    "is_run_id", "OUTPUT_NAME_RE", "is_output_name", "TaskSpec", "EngineSettings", "EffectiveFlags", "LOCKED_FIELDS", "EDITABLE_FIELDS", "ENV_NAMES",
    "SettingsError", "read_settings_file", "SETTINGS_SCHEMA", "RUN_TEMPLATE_ID_RE", "RUN_TEMPLATE_KEYS_MAX", "RUN_TEMPLATE_KEY_CHARS",
    "RUN_TEMPLATE_WORKFLOWS_MAX", "is_run_template_id", "run_template_keys",
]

# Pattern strings, to be used with `re.fullmatch` (never `re.match`: a `$` also accepts a trailing newline).
DEPT_ID_RE = r"^[a-z][a-z0-9-]{1,39}$"      # ORCH's department-id rule, no underscore; also the route dependency and the UI
RUN_ID_RE = r"j2-[A-Za-z0-9_-]{1,120}"      # J2's SAVED regex `j2-[\w-]+`, ASCII only: a run id names a folder
SETTING_KEY_RE = r"J2_[A-Z_]+"
TASK_SCHEMA = "run-spec/1"
SETTINGS_SCHEMA = "engine-settings/1"       # the `schema` of GET /api/engine/settings
CONNECTORS = ("auto", "claude", "codex", "stub")
# An output setting is `auto` (the engine decides once, before J2 starts: `capabilities.select_output`) or a type name in J2's own shape
# (`j2_types.NAME_RE`). This module is read before J2 is imported, so it checks the shape only; whether a name is a type that exists is checked
# where J2 is loaded: the host at preflight and the settings API (D166). There is no closed list of names.
OUTPUT_NAME_RE = r"[a-z][a-z0-9_]{1,40}"
# The first eight are `EngineSettings` fields; the last two (D182) are task-only: the run template this request starts from and the workflows of it.
TASK_SETTING_KEYS = ("J2_OUTPUT", "J2_BUDGET", "J2_BUDGET_CAP", "J2_FIXES", "J2_MEMORY", "J2_SLIM", "J2_RATES", "J2_DECIDE_FOR_ME",
                     "J2_RUN_TEMPLATE", "J2_RUN_TEMPLATE_WORKFLOWS")
RUN_TEMPLATE_ID_RE = r"[a-z0-9-]{1,80}"        # a run template's id (J2 names its folder `library/run-templates/<id>/`)
RUN_TEMPLATE_WORKFLOWS_MAX = 400               # characters of `J2_RUN_TEMPLATE_WORKFLOWS`
RUN_TEMPLATE_KEYS_MAX = 40                     # workflow keys one request may name
RUN_TEMPLATE_KEY_CHARS = 20                    # characters of one key


def is_dept_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(DEPT_ID_RE, value) is not None


def is_output_name(value: object) -> bool:
    """`value` has the shape of a type name (not `auto`)."""
    return isinstance(value, str) and re.fullmatch(OUTPUT_NAME_RE, value) is not None


def is_run_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(RUN_ID_RE, value) is not None


def is_run_template_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(RUN_TEMPLATE_ID_RE, value) is not None


def run_template_keys(value: object) -> Optional[list[str]]:
    """The workflow keys of `J2_RUN_TEMPLATE_WORKFLOWS` (`all`, or a comma list), as J2's `set_run_template` takes them: `[]` is the whole
    template (`all`, an empty text), else the keys in order. None when the value is not that shape (too long, too many keys, a key too long
    or with a character that is not a letter, digit, `-`, `_` or `.`)."""
    if not isinstance(value, str) or len(value) > RUN_TEMPLATE_WORKFLOWS_MAX:
        return None
    keys = [key.strip() for key in value.split(",") if key.strip()]
    if len(keys) > RUN_TEMPLATE_KEYS_MAX or not all(re.fullmatch(rf"[A-Za-z0-9_.-]{{1,{RUN_TEMPLATE_KEY_CHARS}}}", key) for key in keys):
        return None
    return [] if [key.lower() for key in keys] in ([], ["all"]) else keys


class TaskSpec(BaseModel):
    """`task.json`, read by the engine host. Unknown keys are ignored (a newer orchestrator may add some).

    `settings` keeps only keys that fullmatch `J2_[A-Z_]+`; the others are dropped and listed in `dropped_settings`, so the
    host can write one trace line. `upstream` entries are `{dept_id, run_id, title, files}`; `files` are paths relative to
    the upstream run's folder, and the host (not this class) refuses absolute paths, `..` and links that leave it."""

    model_config = ConfigDict(extra="ignore", validate_by_name=True, validate_by_alias=True)

    schema_: Optional[str] = Field(None, alias="schema")
    run_id: str
    task_id: str = Field(min_length=1)
    dept_id: str
    dept_label: str = ""
    scope_id: Optional[str] = None
    scope_label: Optional[str] = None
    user_text: str
    framing: str = ""
    parent_run_id: Optional[str] = None
    seed_from: Optional[str] = None
    upstream: list[dict] = []
    settings: dict[str, str] = {}
    connector: Literal["auto", "claude", "codex", "stub"] = "auto"
    _dropped_settings: list[str] = PrivateAttr(default_factory=list)

    @field_validator("schema_")
    @classmethod
    def _known_schema(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value != TASK_SCHEMA:
            raise ValueError(f"task.json schema must be {TASK_SCHEMA}, not {value!r}")
        return value

    @field_validator("run_id")
    @classmethod
    def _run_id(cls, value: str) -> str:
        if not is_run_id(value):
            raise ValueError(f"run_id must look like j2-<letters, digits, - or _>, not {value[:60]!r}")
        return value

    @field_validator("parent_run_id", "seed_from")
    @classmethod
    def _other_run_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not is_run_id(value):
            raise ValueError(f"must be a run id like j2-..., not {value[:60]!r}")
        return value

    @field_validator("dept_id")
    @classmethod
    def _dept_id(cls, value: str) -> str:
        if not is_dept_id(value):
            raise ValueError(f"dept_id must match {DEPT_ID_RE}, not {value[:60]!r}")
        return value

    @field_validator("user_text")
    @classmethod
    def _user_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("user_text must not be empty")
        return value

    @field_validator("upstream")
    @classmethod
    def _upstream(cls, value: list[dict]) -> list[dict]:
        for i, item in enumerate(value):
            if "dept_id" in item and not is_dept_id(item["dept_id"]):
                raise ValueError(f"upstream[{i}].dept_id must match {DEPT_ID_RE}")
            if "run_id" in item and not is_run_id(item["run_id"]):
                raise ValueError(f"upstream[{i}].run_id must be a run id like j2-...")
            if "title" in item and not isinstance(item["title"], str):
                raise ValueError(f"upstream[{i}].title must be a string")
            files = item.get("files", [])
            if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
                raise ValueError(f"upstream[{i}].files must be a list of strings")
        return value

    @model_validator(mode="after")
    def _keep_job_settings(self) -> "TaskSpec":
        dropped = [key for key in self.settings if not re.fullmatch(SETTING_KEY_RE, key)]
        if dropped:
            self.settings = {key: val for key, val in self.settings.items() if key not in dropped}
            self._dropped_settings = dropped
        return self

    @property
    def dropped_settings(self) -> tuple[str, ...]:
        return tuple(self._dropped_settings)


@dataclass(frozen=True)
class EffectiveFlags:
    """The reuse flags after J2's implications (`EngineSettings.effective()`): each is what J2 will see as on in the run."""

    auto_reuse: bool
    run_templates: bool
    template_library: bool
    artifact_schema: bool


class SettingsError(ValueError):
    """A settings layer holds something that is not a valid setting. The message names the layer."""


class EngineSettings(BaseModel):
    """Every J2 flag with J2's default. Secrets are never fields (the SMTP login is read from `.env` by `paths`, the owner
    override key stays on the server). `delay` is 0 here (J2: 2 s outside mock for free-tier pacing); the router paces."""

    model_config = ConfigDict(extra="forbid")

    output: str = Field("auto", pattern=rf"^(auto|{OUTPUT_NAME_RE})$")      # "auto": the host picks the output for the brief, once, before J2 starts (D129)
    fixes: Literal[0, 1] = 0
    budget: int = Field(100, ge=1, le=100000)
    budget_cap: Optional[int] = Field(None, ge=1, le=100000)      # None: twice the budget
    max_cycles: int = Field(6, ge=1)
    limit_add: int = Field(30, ge=0)
    bargain_minutes: float = Field(15.0, ge=0, allow_inf_nan=False)
    bargain_calls: int = Field(8, ge=0)
    max_turns: int = Field(30, ge=1)
    chat_full_chars: int = Field(60000, ge=1)
    delay: float = Field(0.0, ge=0, allow_inf_nan=False)
    rates: bool = True              # on by default
    slim: bool = True
    memory: bool = True
    realization: bool = True
    change: bool = False            # off by default
    board: bool = False
    artifact_schema: bool = False
    template_library: bool = False
    run_templates: bool = False     # J2 sync 6 (D177): a run can start from a run template (J2_RUN_TEMPLATES); experimental, off
    auto_reuse: bool = False        # the best run template is taken after the first charter, section templates are adapted (J2_AUTO_REUSE); implies the two above
    artifact_library: bool = False  # the content door: a section is served from a finished run of the team (J2_ARTIFACT_LIBRARY); implies auto-reuse
    send_mode: Literal["dry-run", "mock", "live"] = "dry-run"
    send_cap: int = Field(10, ge=0)
    milestone_emails: bool = False
    test_email: str = Field("", max_length=320)
    test_slack_target: str = Field("", max_length=200)
    tap_min: int = Field(44, ge=0)
    chrome: str = Field("", max_length=1024)
    force_audit_fail: int = Field(0, ge=0)                         # test switches
    force_audit_note: str = Field("", max_length=1000)
    force_question: str = Field("", max_length=1000)
    memory_test_lessons: bool = False
    workspace: Literal["auto", "off"] = "auto"      # the workspace capability (D127): agents read the owner's working folder; "off" gives them none
    builder_timeout: float = Field(600, ge=0, allow_inf_nan=False)      # J2 sync 5: seconds a builder's AI call may run before it is stopped and tried once more; 0 = no limit (J2_BUILDER_TIMEOUT)
    decide_for_me: bool = False     # J2 sync 4: the team answers its own questions with the suggested option; the Simple view's switch (J2_DECIDE_FOR_ME)
    reviewer: bool = True           # J2 sync 6 (D179): the reviewer's notes in the run report; read by the host, not by J2 (J2_REVIEWER)
    reviewer_wait: float = Field(120.0, ge=0, allow_inf_nan=False)      # seconds the host waits for the reviewer when a run ends; 0 = do not wait (J2_REVIEWER_WAIT)

    def effective(self) -> "EffectiveFlags":
        """The flags as J2 computes them, once (D178): `auto_reuse` is on when `artifact_library` is; `run_templates` and `template_library` when
        `auto_reuse` is; `artifact_schema` when `template_library` is. J2 does the implying inside the run (`j2_template_lib.enabled`,
        `auto_reuse`, `j2.run_templates_on`, `artifact_schema_on`); the app asks here, so there is one copy of the rule. The settings are not
        rewritten: what the owner chose stays what is stored."""
        reuse = self.auto_reuse or self.artifact_library
        library = self.template_library or reuse
        return EffectiveFlags(auto_reuse=reuse, run_templates=self.run_templates or reuse, template_library=library,
                              artifact_schema=self.artifact_schema or library)

    def to_env(self) -> dict[str, str]:
        """The J2 environment for these settings: `J2_<FIELD>` with "1"/"0" for flags; empty values (an empty string or
        None, such as `budget_cap`) are left out, so J2's own default applies."""
        out = {}
        for name in type(self).model_fields:
            value = getattr(self, name)
            if value is None or value == "":
                continue
            out[ENV_NAMES[name]] = _env_text(value)
        return out

    @classmethod
    def layered(cls, env: Mapping, global_file: Optional[Mapping], dept_file: Optional[Mapping],
                task_settings: Mapping) -> "EngineSettings":
        """defaults < `data/engine.json` < `J2_*` in `env` < the department's `engine.json` < `task_settings`.

        `env` and `task_settings` are read by J2's variable names (anything that is not a setting, such as `J2_RUNS_DIR`, is
        ignored); the two files by field names (an unknown one is an error). An empty value is not set. Flags take
        1/0, true/false, yes/no and on/off; a word that means none of them is an error, where J2 would have quietly
        read it as off (or as on). Raises `SettingsError` naming the layer."""
        merged: dict[str, Any] = {}
        for label, from_env, source in (("data/engine.json", False, global_file), ("the process environment", True, env),
                                        ("the department's engine.json", False, dept_file),
                                        ("the task's settings", True, task_settings)):
            if source is None:
                continue
            if not isinstance(source, Mapping):
                raise SettingsError(f"{label}: must be an object")
            partial = _read_env(label, source) if from_env else dict(source)
            merged.update(_check(label, partial, names=ENV_NAMES if from_env else None))
        return _check("the settings", merged, whole=True)


LOCKED_FIELDS = ("send_mode", "send_cap", "milestone_emails", "test_email", "test_slack_target", "chrome",
                 "force_audit_fail", "force_audit_note", "force_question", "memory_test_lessons")
EDITABLE_FIELDS = tuple(name for name in EngineSettings.model_fields if name not in LOCKED_FIELDS)
ENV_NAMES: dict[str, str] = {name: "J2_" + name.upper() for name in EngineSettings.model_fields}
_FIELD_OF_ENV = {env_name: name for name, env_name in ENV_NAMES.items()}

if not set(LOCKED_FIELDS) <= set(EngineSettings.model_fields):       # a typo here would unlock a dangerous switch
    raise RuntimeError("LOCKED_FIELDS names a field EngineSettings does not have")


def _env_text(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _field_kind(name: str) -> tuple[str, tuple]:
    """('flag' | 'int' | 'float' | 'str' | 'literal', allowed values) of a field, looking through Optional."""
    annotation = EngineSettings.model_fields[name].annotation
    if get_origin(annotation) is Union:
        annotation = next(arg for arg in get_args(annotation) if arg is not type(None))
    if get_origin(annotation) is Literal:
        return "literal", get_args(annotation)
    for kind, py_type in (("flag", bool), ("int", int), ("float", float), ("str", str)):
        if annotation is py_type:
            return kind, ()
    raise RuntimeError(f"settings field {name} has a type read_env cannot parse")


_TRUE_WORDS = ("1", "true", "yes", "on")
_FALSE_WORDS = ("0", "false", "no", "off")


def _parse_env_value(name: str, raw: Any) -> Any:
    """One variable's text as the field's type. An empty value is None (not set); a bad one raises ValueError."""
    text = _env_text(raw)
    if not text.strip():
        return None
    kind, allowed = _field_kind(name)
    word = text.strip().lower()
    if name == "output":        # `auto` or a type name: lower case, checked by shape here so every bad variable of a layer is reported at once
        if not re.fullmatch(rf"auto|{OUTPUT_NAME_RE}", word):
            raise ValueError("must be auto or a type name (lower case letters, digits and _, starting with a letter)")
        return word
    if kind == "str":
        return text
    if kind == "flag" or (kind == "literal" and allowed == (0, 1)):
        if word in _TRUE_WORDS:
            flag = True
        elif word in _FALSE_WORDS:
            flag = False
        else:
            raise ValueError("must be 1 or 0 (or true/false, yes/no, on/off)")
        return int(flag) if kind == "literal" else flag
    if kind == "literal":
        if word not in allowed:
            raise ValueError("must be one of " + ", ".join(map(str, allowed)))
        return word
    try:
        number = float(word)
    except ValueError:
        raise ValueError("must be a number") from None
    if not math.isfinite(number):
        raise ValueError("must be a finite number")
    if kind == "float":
        return number
    if not number.is_integer():
        raise ValueError("must be a whole number")
    return int(number)


def _read_env(label: str, source: Mapping) -> dict[str, Any]:
    out: dict[str, Any] = {}
    problems = []
    for env_name, raw in source.items():
        name = _FIELD_OF_ENV.get(env_name)
        if name is None:
            continue
        try:
            value = _parse_env_value(name, raw)
        except ValueError as exc:
            problems.append(f"{env_name}: {exc}")
            continue
        if value is not None:
            out[name] = value
    if problems:
        raise SettingsError(f"{label}: " + "; ".join(problems))
    return out


def _check(label: str, values: dict[str, Any], *, names: Optional[Mapping[str, str]] = None, whole: bool = False) -> Any:
    """Validate `values` as (part of) the settings. Part: returns the checked values for the same keys. Whole: the model.
    `names` turns a field into the name the layer used for it (J2_BUDGET for budget) in the error message."""
    try:
        model = EngineSettings(**values)
    except ValidationError as exc:
        def called(loc: tuple) -> str:
            return ".".join(str((names or {}).get(str(part), part)) for part in loc) or "value"
        why = "; ".join(f"{called(err['loc'])}: {err['msg']}" for err in exc.errors(include_url=False))
        raise SettingsError(f"{label}: {why}") from None
    return model if whole else {name: getattr(model, name) for name in values}


def read_settings_file(path) -> Optional[dict]:
    """A partial settings file (`data/engine.json` or a department's), or None when it does not exist. A file that is not a
    JSON object is a `SettingsError`: a settings file that is half written must not be read as 'no settings'."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise SettingsError(f"{path}: not valid JSON ({exc})") from None
    if not isinstance(data, dict):
        raise SettingsError(f"{path}: must hold a JSON object")
    return data
