"""Tool connectors (work package CN-8, connectors design 3.9, CD14-CD16).

    profiles       none | sutra | sutra+github; the MCP entry for each CLI (Claude's 0600 file, Codex's `-c` strings); ToolSpec
    mcp_server     `python -m sutra_app.connectors.tools.mcp_server`: the stdlib JSON-RPC server both CLIs start
    sutra_tools    read-only chart, models, graph and atom tools over a ReadModel (SQLite `mode=ro` by default)
    github_tools   read-only GitHub tools over the owner's own `gh`; untrusted wrapper, 20 KB cut, no token in Sutra
    mediated       Claude-held Gmail, Drive and Slack: shown, never implemented

`mcp_server` is not imported here: it runs as `python -m`, and importing it from the package would load it twice.
"""
from .mediated import MediatedConnectors, RefreshTooSoon
from .profiles import (
    PROFILES, ToolError, ToolSpec, claude_mcp_config, claude_mcp_file, codex_mcp_flags, mcp_servers, profile_name, tool_catalog,
    tools_status,
)

__all__ = [
    "PROFILES", "ToolError", "ToolSpec", "claude_mcp_config", "claude_mcp_file", "codex_mcp_flags", "mcp_servers", "profile_name",
    "tool_catalog", "tools_status", "MediatedConnectors", "RefreshTooSoon",
]
