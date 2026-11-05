"""Tool profiles: how a call asks for tools, and the MCP entry each CLI gets (connectors design 3.9, CD14).

A profile is `none` (J2's plain completion), `sutra` or `sutra+github`. `mcp_servers` renders the ONE entry (the app's own
stdlib MCP server) that both CLIs start; `claude_mcp_config` / `claude_mcp_file` turn it into the 0600 JSON file Claude reads
(never on argv, deleted in `finally`), `codex_mcp_flags` into the `-c mcp_servers.<name>.*` strings Codex takes per call. The
server's own env holds `PYTHONPATH` and `SUTRA_DB_RO` (a path, not a secret) and nothing else.

This module also holds `ToolSpec` / `ToolError` and the small argument checker the server uses for every tool, so the tool
modules (`sutra_tools`, `github_tools`) and the server share one definition. It imports nothing heavy at import time.
"""
from __future__ import annotations

import contextlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence

from sutra_app.config import DB_FILENAME

__all__ = [
    "PROFILES", "SERVER_NAME", "SERVER_MODULE", "ToolError", "ToolSpec", "validate_args", "profile_name", "tool_names_of",
    "mcp_servers", "claude_mcp_config", "claude_mcp_file", "codex_mcp_flags", "tool_catalog", "tools_status",
]

PROFILES = ("none", "sutra", "sutra+github")
SERVER_NAME = "sutra"                          # the MCP server name: Claude's tools are mcp__sutra__<tool>
SERVER_MODULE = "sutra_app.connectors.tools.mcp_server"
_KNOWN = ("sutra", "github")
_NAME = re.compile(r"[A-Za-z0-9_-]+")


class ToolError(Exception):
    """A tool failed in a way the model should read: it becomes a tool result with `isError`, never a protocol error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool. `input_schema` is a flat JSON Schema (`validate_args` understands type, enum, pattern, min/max, length)."""

    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], Any]
    read_only: bool = True

    def as_mcp(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema,
                "annotations": {"readOnlyHint": self.read_only}}


def validate_args(schema: Mapping[str, Any], args: Any) -> dict:
    """Check `args` against a flat object schema; returns a copy. Raises ToolError('invalid_arguments', ...) naming the argument."""
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolError("invalid_arguments", "arguments must be an object")
    props = schema.get("properties", {})
    for name in args:
        if name not in props:
            raise ToolError("invalid_arguments", f"unknown argument {name!r} (allowed: {', '.join(sorted(props)) or 'none'})")
    for name in schema.get("required", ()):
        if name not in args:
            raise ToolError("invalid_arguments", f"missing required argument {name!r}")
    for name, value in args.items():
        spec = props[name]
        kind = spec.get("type")
        if kind == "string":
            if not isinstance(value, str):
                raise ToolError("invalid_arguments", f"argument {name!r} must be a string")
            if "\0" in value:
                raise ToolError("invalid_arguments", f"argument {name!r} may not contain NUL")
            if len(value) > spec.get("maxLength", 10_000):
                raise ToolError("invalid_arguments", f"argument {name!r} is longer than {spec.get('maxLength', 10_000)} characters")
            if "pattern" in spec and not re.fullmatch(spec["pattern"], value):
                raise ToolError("invalid_arguments", f"argument {name!r} has a form that is not allowed")
            if "enum" in spec and value not in spec["enum"]:
                raise ToolError("invalid_arguments", f"argument {name!r} must be one of {', '.join(spec['enum'])}")
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ToolError("invalid_arguments", f"argument {name!r} must be an integer")
            low, high = spec.get("minimum"), spec.get("maximum")
            if (low is not None and value < low) or (high is not None and value > high):
                raise ToolError("invalid_arguments", f"argument {name!r} must be from {low} to {high}")
    return dict(args)


# ---- profiles ----------------------------------------------------------------------------------------------------------------

def tool_names_of(tools: Sequence[str]) -> tuple[str, ...]:
    """The normalised profile parts: `("sutra",)`, `("sutra", "github")`; `none` and empty drop out. The connectors' own rule."""
    from ..base import tool_names
    return tool_names(tools)


def profile_name(tools: Sequence[str]) -> str:
    """The profile a tuple of parts stands for: none, sutra, sutra+github (or github when only that part is asked)."""
    parts = tool_names_of(tools)
    return "+".join(parts) if parts else "none"


def _root() -> str:
    import sutra_app
    return str(Path(sutra_app.__file__).resolve().parent.parent)


def mcp_servers(cfg: Any, tools: Sequence[str], *, readmodel: Optional[str] = None) -> dict[str, Any]:
    """The MCP entry for a tool profile: `{"sutra": {command, args, env}}`, or `{}` for the profile `none`.

    `command` is `cfg.python`; `--profile` lists the parts; `--gh-exe` appears only when `cfg.gh_exe` is not plain `gh`;
    `--readmodel pkg.mod:factory` only when given. The env is `PYTHONPATH` (the checkout root) and `SUTRA_DB_RO`
    (`<data_dir>/db.sqlite3`): no token, no key, no other variable."""
    parts = tool_names_of(tools)
    if not parts:
        return {}
    args = ["-m", SERVER_MODULE, "--profile", ",".join(parts)]
    if "github" in parts and getattr(cfg, "gh_exe", "gh") != "gh":
        args += ["--gh-exe", str(cfg.gh_exe)]
    if readmodel:
        args += ["--readmodel", readmodel]
    return {SERVER_NAME: {"command": cfg.python, "args": args,
                          "env": {"PYTHONPATH": _root(), "SUTRA_DB_RO": str(Path(cfg.data_dir) / DB_FILENAME)}}}


def claude_mcp_config(cfg: Any, tools: Sequence[str], *, readmodel: Optional[str] = None) -> str:
    """The text of Claude's `--mcp-config` file."""
    return json.dumps({"mcpServers": mcp_servers(cfg, tools, readmodel=readmodel)}, ensure_ascii=False)


@contextlib.contextmanager
def claude_mcp_file(cfg: Any, tools: Sequence[str], *, parent: Optional[Path] = None,
                    readmodel: Optional[str] = None) -> Iterator[Path]:
    """A 0600 `mcp.json` in a private directory (mkdtemp makes it 0700), removed with its directory when the block ends, whatever happened."""
    from ..base import write_private_file
    directory = Path(tempfile.mkdtemp(prefix="sutra-mcp-", dir=str(parent) if parent else None))
    try:
        path = directory / "mcp.json"
        write_private_file(path, claude_mcp_config(cfg, tools, readmodel=readmodel))
        yield path
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _toml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def codex_mcp_flags(cfg: Any, tools: Sequence[str], *, readmodel: Optional[str] = None) -> list[str]:
    """`-c mcp_servers.<name>.command/args/env=...` for one Codex call: TOML values on the argv, nothing on disk."""
    argv: list[str] = []
    for name, server in mcp_servers(cfg, tools, readmodel=readmodel).items():
        if not _NAME.fullmatch(name):
            raise ValueError(f"MCP server name {name!r} is not usable")
        env = ",".join(f"{k}={_toml(str(v))}" if _NAME.fullmatch(k) else f"{_toml(k)}={_toml(str(v))}" for k, v in server["env"].items())
        argv += ["-c", f"mcp_servers.{name}.command={_toml(server['command'])}",
                 "-c", f"mcp_servers.{name}.args=[{','.join(_toml(str(a)) for a in server['args'])}]",
                 "-c", f"mcp_servers.{name}.env={{{env}}}"]
    return argv


# ---- the catalog (GET /api/connectors/tools) ----------------------------------------------------------------------------------

def tool_catalog(profile: str = "sutra+github") -> list[dict]:
    """`[{name, description, read_only: true}]` for the tools a profile offers (all of them, whatever a ReadModel supports)."""
    from . import github_tools, sutra_tools
    parts = tool_names_of((profile,))
    specs: list[ToolSpec] = []
    if "sutra" in parts:
        specs += sutra_tools.tool_specs(None)
    if "github" in parts:
        specs += github_tools.tool_specs(None)
    return [{"name": s.name, "description": s.description, "read_only": s.read_only} for s in specs]


def tools_status(cfg: Any, *, env: Optional[Mapping[str, str]] = None) -> dict[str, bool]:
    """`{"sutra": True, "github": <gh auth status exits 0>}` for the status route."""
    from . import github_tools
    return {"sutra": True, "github": github_tools.gh_available(str(cfg.gh_exe), env=env)}
