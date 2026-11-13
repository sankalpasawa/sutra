"""The app's settings: closed, read from `SUTRA_*` variables, with the secrets kept out of every dump (orchestrator 3.1, 6.4).

    from sutra_app.config import Settings
    settings = Settings.load()                       # environment, then the .env file for the override key
    settings = Settings.load(port=9000, offline=True)  # keyword arguments (the CLI flags) win over the environment

The token (`SUTRA_TOKEN`, else random) has at least 16 visible characters and travels in the header `X-Sutra-Token`
only. The owner-override key (`J2_OVERRIDE_KEY`, in the environment or in the file named by `SUTRA_ENV_FILE`) never
leaves the server: both fields are excluded from `model_dump`, `repr` and JSON, and `public()` (what `/api/config`
shows) lists neither. The server binds loopback only: a non-loopback `SUTRA_HOST` is refused at load.
"""
import os
import re
import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, ValidationError, field_validator, model_validator

__all__ = [
    "Settings", "SettingsError", "ENV_NAMES", "LOOPBACK_HOSTS", "OVERRIDE_KEY_NAME", "MIN_TOKEN_LENGTH", "DB_FILENAME", "project_root",
    "default_data_dir", "default_env_file", "read_env_file", "env_value", "new_token",
]

MIN_TOKEN_LENGTH = 16
DB_FILENAME = "db.sqlite3"                      # the database file inside the data folder (the Sutra tools open the same name, G04)
OVERRIDE_KEY_NAME = "J2_OVERRIDE_KEY"          # the name J2 uses in the environment and in `.env`
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")    # what TrustedHostMiddleware allows too (D11, D81)
# field -> environment variable (design 6.4); `override_key` is read from OVERRIDE_KEY_NAME
ENV_NAMES = {
    "data_dir": "SUTRA_DATA_DIR", "host": "SUTRA_HOST", "port": "SUTRA_PORT", "token": "SUTRA_TOKEN",
    "connector": "SUTRA_CONNECTOR", "engine": "SUTRA_ENGINE", "offline": "SUTRA_OFFLINE", "chat_timeout": "SUTRA_CHAT_TIMEOUT",
    "chat_attempts": "SUTRA_CHAT_ATTEMPTS", "max_runs": "SUTRA_MAX_RUNS", "max_live": "SUTRA_MAX_LIVE",
    "watch_ms": "SUTRA_WATCH_MS", "live": "SUTRA_LIVE", "env_file": "SUTRA_ENV_FILE",
}
_TRUE = ("1", "true", "yes", "on")
_FALSE = ("", "0", "false", "no", "off")


class SettingsError(ValueError):
    """A setting is missing, malformed or refused. The message names the variable or field, never a secret value."""


def project_root() -> Path:
    """The folder that holds the `sutra_app` package: the checkout in development."""
    return Path(__file__).resolve().parents[1]


def default_data_dir(environ: Mapping[str, str] | None = None) -> Path:
    """`SUTRA_DATA_DIR`; else `<project>/data` when the package sits in a checkout (a `pyproject.toml` beside it); else
    `~/.sutra-pro` (an installed app, D88: it never reads the repo's data folder)."""
    env = os.environ if environ is None else environ
    named = (env.get(ENV_NAMES["data_dir"]) or "").strip()
    if named:
        return Path(named).expanduser()
    root = project_root()
    if (root / "pyproject.toml").is_file():
        return root / "data"
    return Path.home() / ".sutra-pro"


def default_env_file(environ: Mapping[str, str] | None = None) -> Path:
    """The file named by `SUTRA_ENV_FILE`, else `<project>/.env` in a checkout (a `pyproject.toml` beside the package), else
    `<data dir>/.env` (an installed app: the package sits in site-packages, where nobody keeps a `.env`, G03)."""
    env = os.environ if environ is None else environ
    named = (env.get(ENV_NAMES["env_file"]) or "").strip()
    if named:
        return Path(named).expanduser()
    root = project_root()
    return root / ".env" if (root / "pyproject.toml").is_file() else default_data_dir(env) / ".env"


_INLINE_COMMENT = re.compile(r"\s+#")


def env_value(text: str) -> str:
    """The value of a `.env` line from the text after its `=`, as dotenv tools read it. A value in double quotes ends at the closing quote
    (`\\"` and `\\\\` inside it are a quote and a backslash), one in single quotes at the next single quote, and what follows the closing
    quote (a comment) is not part of it. An unquoted value ends at a ` #` (space, then a hash: a comment), a `#` inside it stays, and its
    quote marks are kept. A quote that never closes is dropped from the ends, as before."""
    text = text.strip()
    if text[:1] in ('"', "'"):
        quote, chars, i = text[0], [], 1
        while i < len(text):
            char = text[i]
            if char == quote:
                return "".join(chars)
            if quote == '"' and char == "\\" and text[i + 1:i + 2] in ('"', "\\"):
                char, i = text[i + 1], i + 1
            chars.append(char)
            i += 1
        return text.strip('"').strip("'")                       # no closing quote: the old reading
    return _INLINE_COMMENT.split(text, maxsplit=1)[0].strip()


def read_env_file(path: str | os.PathLike[str] | None, *, whole_line: bool = False) -> dict[str, str]:
    """Every `KEY=value` pair of a `.env` file as text (`env_value` reads each value). Blank lines and `#` comments are skipped, a leading
    `export ` is understood, a later line wins. A missing or unreadable file is an empty file. This is only a reader: nothing is put into
    `os.environ`. `whole_line=True` keeps everything after the `=` (a comment too, the quote marks of the ends dropped): another tool may read
    a line that way (Docker's `--env-file` does), so the redactor hides that reading as well."""
    if path is None:
        return {}
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()       # a byte-order mark is not part of the first name
    except (OSError, UnicodeDecodeError):
        return {}
    pairs: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        if key:
            pairs[key] = value.strip().strip('"').strip("'") if whole_line else env_value(value)
    return pairs


def new_token() -> str:
    """A fresh per-launch token: 32 URL-safe characters, never written to disk."""
    return secrets.token_urlsafe(24)


Token = Annotated[str, StringConstraints(pattern=r"^[\x21-\x7e]{16,200}$")]      # visible ASCII only: it travels in a header


class Settings(BaseModel):
    """Closed (`extra="forbid"`) and frozen. `token` and `override_key` are secrets: excluded from dumps and `repr`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_dir: Path
    host: str = "127.0.0.1"
    port: int = Field(8780, ge=0, le=65535)
    token: Token = Field(default_factory=new_token, exclude=True, repr=False)
    connector: Literal["auto", "claude", "codex", "stub"] = "auto"
    engine: Literal["process", "fake"] = "process"
    offline: bool = False
    chat_timeout: float = Field(120.0, gt=0, le=3600, allow_inf_nan=False)
    chat_attempts: int = Field(3, ge=1, le=5)
    max_runs: int = Field(3, ge=1, le=64)
    max_live: int = Field(12, ge=1, le=256)
    watch_ms: int = Field(400, ge=20, le=10_000)
    live: bool = False
    override_key: SecretStr | None = Field(None, exclude=True, repr=False)
    env_file: Path

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if value not in LOOPBACK_HOSTS:
            raise ValueError(f"the server binds loopback only (D11): host must be one of {', '.join(LOOPBACK_HOSTS)}, not {value[:60]!r}")
        return value

    @field_validator("override_key")
    @classmethod
    def _key_not_blank(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            return None          # an empty J2_OVERRIDE_KEY= line means no key, not a key that every message starts with
        return value

    @model_validator(mode="after")
    def _live_covers_running(self) -> "Settings":
        if self.max_live < self.max_runs:
            raise ValueError(f"max_live ({self.max_live}) must be at least max_runs ({self.max_runs}): it bounds every live process")
        return self

    # ---- loading --------------------------------------------------------------------------------------------

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None, **overrides: Any) -> "Settings":
        """Defaults, then the environment (`ENV_NAMES`), then `overrides` (field names; None means 'not given').
        The override key comes from `J2_OVERRIDE_KEY` in the environment, else from the `.env` file. Raises
        `SettingsError` with the variable or field named; a rejected token or key value is never quoted."""
        env = os.environ if environ is None else environ
        unknown = sorted(set(overrides) - set(cls.model_fields))
        if unknown:
            raise SettingsError(f"unknown setting: {', '.join(unknown)}")
        values: dict[str, Any] = {}
        for field, name in ENV_NAMES.items():
            raw = env.get(name)
            if raw is not None and field not in ("data_dir", "env_file"):
                values[field] = cls._parse_env(field, name, raw)
        values["data_dir"] = default_data_dir(env)
        values["env_file"] = default_env_file(env)
        for field, value in overrides.items():
            if value is not None:
                values[field] = value
        # absolute: a team's engine runs in another working directory and is handed paths under this folder (`--data-dir ./x` crashed every run)
        values["data_dir"] = Path(os.path.abspath(Path(values["data_dir"]).expanduser()))
        if "override_key" not in values:
            key = env.get(OVERRIDE_KEY_NAME)
            if key is None:
                key = read_env_file(values["env_file"]).get(OVERRIDE_KEY_NAME)
            if key:
                values["override_key"] = key
        if isinstance(values.get("override_key"), str):
            values["override_key"] = SecretStr(values["override_key"])
        try:
            return cls(**values)
        except ValidationError as exc:
            raise SettingsError(cls._explain(exc)) from None

    @staticmethod
    def _parse_env(field: str, name: str, raw: str) -> Any:
        """One environment value as the field's type; a malformed one is a SettingsError that names the variable."""
        annotation = Settings.model_fields[field].annotation
        text = raw.strip()
        try:
            if annotation is bool:
                if text.lower() in _TRUE:
                    return True
                if text.lower() in _FALSE:
                    return False
                raise ValueError("expected 1 or 0")
            if annotation is int:
                return int(text)
            if annotation is float:
                return float(text)
        except ValueError:
            raise SettingsError(f"{name} is not valid: expected {'a whole number' if annotation is int else 'a number' if annotation is float else '1 or 0'}") from None
        return text

    @staticmethod
    def _explain(exc: ValidationError) -> str:
        """pydantic's errors as one line each, with the field named and the offending input left out (it may be a secret)."""
        lines = []
        for err in exc.errors(include_url=False, include_input=False):
            where = ".".join(str(part) for part in err["loc"]) or "settings"
            name = ENV_NAMES.get(where, OVERRIDE_KEY_NAME if where == "override_key" else where)
            msg = str(err["msg"]).removeprefix("Value error, ")
            if where == "token":
                msg = f"the token must be {MIN_TOKEN_LENGTH} to 200 visible characters with no spaces"
            lines.append(f"{name}: {msg}")
        return "; ".join(lines)

    # ---- what other code may show and where files live ---------------------------------------------------------

    def public(self) -> dict[str, Any]:
        """The non-secret settings, as `GET /api/config` shows them. Never the token or the override key."""
        return {
            "data_dir": str(self.data_dir), "host": self.host, "port": self.port, "connector": self.connector,
            "engine": self.engine, "offline": self.offline, "chat_timeout": self.chat_timeout,
            "chat_attempts": self.chat_attempts, "max_runs": self.max_runs, "max_live": self.max_live,
            "watch_ms": self.watch_ms, "live": self.live,
        }

    @property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def log_path(self) -> Path:
        return self.logs_dir / "server.log"

    @property
    def departments_dir(self) -> Path:
        return self.data_dir / "departments"

    @property
    def connectors_dir(self) -> Path:
        return self.data_dir / "connectors"

    def department_dir(self, dept_id: str) -> Path:
        """`<data>/departments/<dept id>`: the id must be a plain folder name (no separator, no dot parts)."""
        if not dept_id or dept_id in (".", "..") or "/" in dept_id or "\\" in dept_id or "\x00" in dept_id:
            raise SettingsError(f"not a department id: {dept_id[:60]!r}")
        return self.departments_dir / dept_id

    def ensure_dirs(self) -> None:
        """Create the data folder, `logs/` and `departments/` (mode 0700: the app holds the owner's work). Idempotent."""
        for path in (self.data_dir, self.logs_dir, self.departments_dir):
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
