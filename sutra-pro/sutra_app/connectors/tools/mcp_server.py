"""The app's own MCP server: `python -m sutra_app.connectors.tools.mcp_server --profile sutra[,github]` (design 3.9, CD14).

Newline-delimited JSON-RPC 2.0 over stdin and stdout, standard library only. It answers `initialize` by echoing the client's
`protocolVersion` (2025-11-25 and 2025-06-18 were seen), ignores notifications, serves `ping`, `tools/list` and `tools/call`
(result `content: [{type: "text", text: <json>}]`, `isError`), and answers `server/discover` and every unknown method with
error -32601. A malformed line gets -32700 and the server keeps running. All tools are read-only. stdout carries protocol
lines only; diagnostics go to stderr.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Callable, Iterable, Optional, TextIO

from .profiles import ToolError, ToolSpec, tool_names_of, validate_args

__all__ = ["McpServer", "build_server", "serve", "main", "DEFAULT_PROTOCOL", "MAX_RESULT_CHARS"]

DEFAULT_PROTOCOL = "2025-06-18"
MAX_RESULT_CHARS = 100_000
SERVER_INFO = {"name": "sutra", "title": "Sutra read tools", "version": "1"}

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def encode_result(value: Any, limit: int = MAX_RESULT_CHARS) -> str:
    """The JSON text of a tool result; over `limit` characters it becomes `{"truncated": true, "text": <first limit characters>}`."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return text
    return json.dumps({"truncated": True, "limit": limit, "text": text[:limit]}, ensure_ascii=False, separators=(",", ":"))


class McpServer:
    """The protocol, free of I/O: `handle(message) -> response dict or None`. `tools` may be a callable so that a lazy check
    (is `gh` signed in?) runs at the first `tools/list` or `tools/call`, not at start-up."""

    def __init__(self, tools: "Iterable[ToolSpec] | Callable[[], Iterable[ToolSpec]]") -> None:
        self._tools_source = tools
        self._tools: Optional[dict[str, ToolSpec]] = None

    @property
    def tools(self) -> dict[str, ToolSpec]:
        if self._tools is None:
            source = self._tools_source() if callable(self._tools_source) else self._tools_source
            self._tools = {t.name: t for t in source}
        return self._tools

    def handle_line(self, line: str) -> Optional[dict]:
        line = line.strip()
        if not line:
            return None
        try:
            message = json.loads(line)
        except ValueError:
            return _error(None, PARSE_ERROR, "parse error: the line is not JSON")
        return self.handle(message)

    def handle(self, message: Any) -> Optional[dict]:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            if isinstance(message, dict) and ("result" in message or "error" in message):
                return None                                   # a response to a request we never sent: ignore
            msg_id = message.get("id") if isinstance(message, dict) and isinstance(message.get("id"), (str, int)) else None
            return _error(msg_id, INVALID_REQUEST, "invalid request: expected a JSON-RPC 2.0 object with a method")
        method, params = message["method"], message.get("params")
        if "id" not in message:
            return None                                       # a notification: never answered
        msg_id = message["id"]
        if isinstance(msg_id, bool) or not isinstance(msg_id, (str, int)):
            return _error(None, INVALID_REQUEST, "invalid request: id must be a string or an integer")
        try:
            if method == "initialize":
                return self._initialize(msg_id, params)
            if method == "ping":
                return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
            if method == "tools/list":
                return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [t.as_mcp() for t in self.tools.values()]}}
            if method == "tools/call":
                return self._call(msg_id, params)
        except Exception as exc:                              # a bug in a tool must not end the server
            print(f"mcp_server: internal error in {method}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return _error(msg_id, INTERNAL_ERROR, "internal error")
        return _error(msg_id, METHOD_NOT_FOUND, f"method not found: {method}")

    def _initialize(self, msg_id: Any, params: Any) -> dict:
        version = params.get("protocolVersion") if isinstance(params, dict) else None
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": version if isinstance(version, str) and version else DEFAULT_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER_INFO}}

    def _call(self, msg_id: Any, params: Any) -> dict:
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _error(msg_id, INVALID_PARAMS, "tools/call needs params.name")
        spec = self.tools.get(params["name"])
        if spec is None:
            return _error(msg_id, INVALID_PARAMS, f"unknown tool: {params['name']}")
        try:
            args = validate_args(spec.input_schema, params.get("arguments"))
            text, is_error = encode_result(spec.handler(args)), False
        except ToolError as exc:
            text, is_error = encode_result({"error": {"code": exc.code, "message": exc.message}}), True
        except Exception as exc:                              # a bug in one tool: the model reads it, the server lives on
            print(f"mcp_server: {spec.name} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            text, is_error = encode_result({"error": {"code": "internal", "message": f"{spec.name} failed unexpectedly"}}), True
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": text}], "isError": is_error}}


def serve(server: McpServer, stdin: TextIO, stdout: TextIO) -> None:
    """Read lines until EOF; write one JSON line per answer, flushed."""
    for line in stdin:
        response = server.handle_line(line)
        if response is not None:
            stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()


def build_server(profile: str, *, db_path: Optional[str] = None, readmodel: Optional[str] = None, gh_exe: str = "gh") -> McpServer:
    """The server for a profile (`sutra`, `github`, `sutra,github` or `sutra+github`). Raises ValueError for a bad profile or
    a ReadModel that cannot be built. The GitHub tools appear only while `gh auth status` exits 0 (checked once, lazily)."""
    from . import github_tools, sutra_tools
    parts = tool_names_of(tuple(p for p in profile.replace("+", ",").split(",") if p.strip()))
    model = sutra_tools.load_readmodel(readmodel, db_path) if "sutra" in parts else None
    gh = github_tools.GithubTools(gh_exe) if "github" in parts else None

    def tools() -> list[ToolSpec]:
        out: list[ToolSpec] = []
        if model is not None:
            out += sutra_tools.tool_specs(model)
        if gh is not None and gh.available():
            out += github_tools.tool_specs(gh)
        return out

    return McpServer(tools)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="sutra_app.connectors.tools.mcp_server", description="Sutra's read-only MCP tool server")
    parser.add_argument("--profile", required=True, help="sutra, github, sutra,github or sutra+github")
    parser.add_argument("--readmodel", default=None, help="pkg.mod:factory; called with the database path")
    parser.add_argument("--db", default=None, help="the SQLite file (default: $SUTRA_DB_RO)")
    parser.add_argument("--gh-exe", default="gh", help="the gh executable")
    try:
        args = parser.parse_args(argv)
        server = build_server(args.profile, db_path=args.db or os.environ.get("SUTRA_DB_RO"), readmodel=args.readmodel, gh_exe=args.gh_exe)
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        print(f"mcp_server: {exc}", file=sys.stderr)
        return 2
    stdin = open(sys.stdin.fileno(), "r", encoding="utf-8", errors="replace", closefd=False)
    stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False)
    try:
        serve(server, stdin, stdout)
    except BrokenPipeError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
