"""Configuration: process environment first, then prototypes/pulse/.env for keys unset or empty in the shell.

Pure: load() returns a Config and never changes os.environ (architecture D-4). Error messages name the key,
never its value (FR-33).
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from errors import PulseError

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
ENV_FILE = HERE / ".env"
MOCK_DOMAIN = "example.test"

KEYS = (
    "PULSE_MOCK", "PULSE_SA_KEY_PATH", "PULSE_DOMAIN", "PULSE_ALLOWLIST", "PULSE_OUT_DIR",
    "PULSE_STATE_DIR", "PULSE_RETENTION_DAYS", "PULSE_MOCK_SCENARIO", "PULSE_DEBUG",
)
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


@dataclass(frozen=True)
class Config:
    mock: bool
    domain: str
    allowlist: Path | None
    sa_key_path: Path | None
    out_dir: Path
    state_dir: Path
    retention_days: int
    scenario: str
    debug: bool


def read_env_file(path: Path) -> dict:
    """KEY=value lines; blank and # lines skipped; surrounding quotes stripped. Missing file gives {}."""
    out = {}
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return out
    except OSError:
        raise PulseError("config_invalid", f"Could not read the config file {path}.")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _expand(value: str, home: Path) -> Path:
    if value == "~":
        return home
    if value.startswith("~/"):
        return home / value[2:]
    return Path(value)


def scenario_names(fixtures_dir: Path = FIXTURES) -> set:
    try:
        data = json.loads((fixtures_dir / "scenarios.json").read_text(encoding="utf-8"))
        return set(data)
    except (OSError, ValueError):
        return {"default"}


def load(environ: Mapping[str, str], env_file: Path, need_live_keys: bool) -> Config:
    file_vals = read_env_file(env_file)

    def get(key: str) -> str:
        shell = (environ.get(key) or "").strip()
        return shell if shell else (file_vals.get(key) or "").strip()

    mock_raw = get("PULSE_MOCK")
    if mock_raw not in ("", "0", "1"):
        raise PulseError("config_invalid", "PULSE_MOCK must be 1, 0 or unset.")
    mock = mock_raw == "1"

    home = Path(environ.get("HOME") or Path.home())

    ret_raw = get("PULSE_RETENTION_DAYS") or "30"
    try:
        retention = int(ret_raw)
    except ValueError:
        retention = 0
    if not 1 <= retention <= 3650:
        raise PulseError("config_invalid", "PULSE_RETENTION_DAYS must be a whole number from 1 to 3650.")

    out_dir = _expand(get("PULSE_OUT_DIR") or "~/.sutra-pulse/out", home)
    state_dir = _expand(get("PULSE_STATE_DIR") or "~/.sutra-pulse/state", home)
    debug = get("PULSE_DEBUG") == "1"

    scenario = get("PULSE_MOCK_SCENARIO") or "default"
    if mock and scenario != "default" and scenario not in scenario_names():
        raise PulseError("config_invalid",
                         "PULSE_MOCK_SCENARIO must name a scenario in fixtures/scenarios.json.")

    if mock:
        # R-2 / D-5: mock never uses live values, so a real .env cannot point mock at a real domain.
        return Config(mock=True, domain=MOCK_DOMAIN, allowlist=FIXTURES / "allowlist.txt", sa_key_path=None,
                      out_dir=out_dir, state_dir=state_dir, retention_days=retention, scenario=scenario,
                      debug=debug)

    key_raw, domain_raw, allow_raw = get("PULSE_SA_KEY_PATH"), get("PULSE_DOMAIN"), get("PULSE_ALLOWLIST")
    if need_live_keys:
        for key, val in (("PULSE_SA_KEY_PATH", key_raw), ("PULSE_DOMAIN", domain_raw),
                         ("PULSE_ALLOWLIST", allow_raw)):
            if not val:
                raise PulseError("config_missing",
                                 f"Add {key} to prototypes/pulse/.env, or set PULSE_MOCK=1 to use the fixture inbox.")
    domain = domain_raw.lower()
    if domain and ("@" in domain or not _DOMAIN_RE.match(domain)):
        raise PulseError("config_invalid", "PULSE_DOMAIN must be a lowercase domain such as example.com, with no @.")
    return Config(mock=False, domain=domain, allowlist=_expand(allow_raw, home) if allow_raw else None,
                  sa_key_path=_expand(key_raw, home) if key_raw else None, out_dir=out_dir,
                  state_dir=state_dir, retention_days=retention, scenario=scenario, debug=debug)
