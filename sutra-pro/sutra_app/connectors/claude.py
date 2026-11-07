"""`ClaudeConnector`: `claude -p` driven in stream-json (connectors design 3.4, D28).

    claude -p --output-format stream-json --verbose --model <alias|full> --effort <e> --system-prompt <text|file>
      --tools "" --strict-mcp-config --disable-slash-commands --setting-sources ""
      [--no-session-persistence | --session-id <uuid> | --resume <uuid>] [--include-partial-messages]
      [--json-schema <one line>] [--input-format stream-json] [--mcp-config <file> --restricted ...] [--max-budget-usd <left>]

The prompt goes on stdin, never argv. The final `result` line decides; failures are classified by `assistant.error` first,
then by the result's fields, then by stderr (`CLAUDE_ERROR_MAP` is the table of 3.4 as data, rows C1 to C25). `is_error`
and `subtype` are separate facts: a failed call can carry `subtype "success"`.

Counters: `result.usage` is per turn; `total_cost_usd` and `modelUsage` are cumulative for a session, so a turn's usd is the
difference to the session's `cum_usd`; a counter that goes backwards (new session, CLI change) is taken whole (3.8).
Everything here is deterministic given the child's output.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Optional

from sutra_app.config import DB_FILENAME

from .base import LineParser, ModelConnector, TurnPlan, write_private_file
from .errors import (
    AccountBlockedError, CallCancelledError, CallTimeoutError, ConnectorError, CliMissingError, CrashedError, EmptyReplyError,
    EnvelopeExceededError, FlagUnsupportedError, InvalidRequestError, ModelNotFoundError, NotSignedInError, OverloadedError,
    ProtocolError, ProviderError, QuotaError, RateLimitedError, ReplyTruncatedError, ServerError, SessionLostError,
    StructuredError,
)
from .models import AuthStatus, Capabilities, ConnectorEvent, ModelInfo, Quota, SessionState, TurnResult, Usage
from .process import Command, ExitInfo
from .quota_windows import windows_from_claude
from .workdir import READ_TOOLS

__all__ = ["ClaudeConnector", "ClaudeParser", "CLAUDE_ERROR_MAP", "SYSTEM_FILE_THRESHOLD", "PROBED_FLAGS", "MODEL_ENV_NAMES"]

SYSTEM_FILE_THRESHOLD = 20000        # a system prompt longer than this goes in a 0600 file (J2 llm.py:117-123)
MODEL_ENV_NAMES = ("SUTRA_CLAUDE_MODEL", "CLAUDE_CLI_MODEL")     # override the policy's model, first one wins
PROBED_FLAGS = (
    "--output-format", "--verbose", "--model", "--effort", "--system-prompt", "--tools", "--strict-mcp-config",
    "--disable-slash-commands", "--setting-sources", "--no-session-persistence", "--session-id", "--resume",
    "--include-partial-messages", "--json-schema", "--input-format", "--mcp-config", "--restricted", "--allowedTools",
    "--permission-mode", "--permission-prompts", "--max-budget-usd", "--disallowedTools",
)
_MCP_SERVER = "sutra"
_ALLOWED_TOOLS = f"mcp__{_MCP_SERVER}__*"
# with an owner's working folder (GAP3-workdir): the only tools are the four read-only ones, and everything that writes, runs a command or
# reaches the network is denied by name as well, so no setting or later default can widen it
_DENIED_TOOLS = ("Bash", "PowerShell", "Edit", "MultiEdit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Task", "Agent", "TodoWrite")
_IMAGE_MAGIC = ((b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"),
                (b"%PDF-", "application/pdf"))        # a PDF goes as a document block (ABS-4)
_RESULT_TEXT_CHARS = 300             # how much of the CLI's own text an error keeps
_AUTH_MARKERS = ("not logged in", "please run /login", "login expired", "oauth token revoked")

# The table of 3.4 as data: row id -> the error code it must produce. The tests run one case per row.
CLAUDE_ERROR_MAP: dict[str, str] = {
    "C1": "cli_missing", "C2": "cli_flag_unsupported", "C3a": "invalid_request", "C3b": "cli_flag_unsupported",
    "C4": "not_signed_in", "C5": "not_signed_in", "C6a": "account_blocked", "C6b": "account_blocked", "C6c": "account_blocked",
    "C7": "quota", "C8": "rate_limited", "C9": "quota", "C10": "overloaded", "C11": "server_error", "C12": "invalid_request",
    "C13": "model_not_found", "C14": "reply_truncated", "C15": "structured", "C16": "session_lost", "C17": "provider_error",
    "C18": "envelope_exceeded", "C19a": "not_signed_in", "C19b": "not_signed_in", "C19c": "not_signed_in",
    "C19d": "rate_limited", "C19e": "server_error", "C20": "crashed", "C21": "protocol_error", "C22": "timeout",
    "C23": "cancelled", "C24": "empty_reply", "C25": "ok",
}


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("type") == "text")
    return ""


def _quota_of(info: Mapping[str, Any]) -> Quota:
    status = {"allowed": "ok", "allowed_warning": "warning", "rejected": "exhausted"}.get(str(info.get("status")), "unknown")
    window = info.get("rateLimitType")
    window = window if isinstance(window, str) else None
    windows = info.get("unifiedWindows")
    used = None
    if isinstance(windows, Mapping) and window in windows and isinstance(windows[window], Mapping):
        used = windows[window].get("utilization")
    if used is None:
        used = info.get("utilization")
    resets = info.get("resetsAt")
    return Quota(status=status, window=window,
                 used=float(used) if isinstance(used, (int, float)) and not isinstance(used, bool) else None,
                 resets_at=float(resets) if isinstance(resets, (int, float)) and not isinstance(resets, bool) else None,
                 source="rate_limit_event", windows=windows_from_claude(info))


class ClaudeParser(LineParser):
    """Stream-json lines -> events, then the `result` line -> a TurnResult or the error of the table in 3.4."""

    provider = "claude"

    def __init__(self, plan: TurnPlan, *, version: Optional[str] = None) -> None:
        self.plan = plan
        self.version = version
        self.skipped = 0
        self.objects = 0
        self.session_id: Optional[str] = None
        self.init_model: Optional[str] = None
        self.assistant_error: Optional[str] = None
        self.assistant_text = ""
        self.quota: Optional[Quota] = None
        self.result: Optional[dict] = None
        self.cum_usd = None
        self.cum_usage = None

    # ---- lines -> events -----------------------------------------------------------------------------------------------------
    def feed(self, line: str) -> list[ConnectorEvent]:
        try:
            obj = json.loads(line)
        except ValueError:
            obj = None
        if not isinstance(obj, dict):
            self.skipped += 1                    # noise between events (C25): ignored, counted
            return []
        self.objects += 1
        kind = obj.get("type")
        if isinstance(obj.get("session_id"), str):
            self.session_id = obj["session_id"]
        handler = getattr(self, f"_on_{kind}", None) if isinstance(kind, str) and kind.isidentifier() else None
        return handler(obj) if handler is not None else []        # an unknown type is ignored

    def _on_system(self, obj: dict) -> list[ConnectorEvent]:
        if obj.get("subtype") != "init":
            return []
        self.init_model = obj.get("model") if isinstance(obj.get("model"), str) else None
        servers = obj.get("mcp_servers") if isinstance(obj.get("mcp_servers"), list) else []
        events = [ConnectorEvent(kind="started", data={
            "session_id": obj.get("session_id"), "model": self.init_model,
            "tools": obj.get("tools") if isinstance(obj.get("tools"), list) else [], "mcp_servers": servers})]
        for server in servers:
            if isinstance(server, dict) and server.get("status") != "connected":
                events.append(ConnectorEvent(kind="notice", data={
                    "text": f"MCP server {server.get('name')} is {server.get('status')}, not connected",
                    "server": server.get("name"), "status": server.get("status")}))
        return events

    def _on_stream_event(self, obj: dict) -> list[ConnectorEvent]:
        if not self.plan.partials:
            return []
        event = obj.get("event")
        if not isinstance(event, dict) or event.get("type") != "content_block_delta":
            return []
        delta = event.get("delta")
        if not isinstance(delta, dict):
            return []
        if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
            return [ConnectorEvent(kind="text_delta", data={"text": delta["text"], "kind": "text"})]
        if delta.get("type") == "input_json_delta" and isinstance(delta.get("partial_json"), str):
            return [ConnectorEvent(kind="text_delta", data={"text": delta["partial_json"], "kind": "json"})]
        return []

    def _on_assistant(self, obj: dict) -> list[ConnectorEvent]:
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        content = message.get("content") if isinstance(message.get("content"), list) else []
        if isinstance(obj.get("error"), str) and self.assistant_error is None:
            self.assistant_error = obj["error"]
        events: list[ConnectorEvent] = []
        errored = isinstance(obj.get("error"), str) or obj.get("is_api_error_message") is True
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                self.assistant_text += block["text"]
                if not errored:                   # an error's text is not the model's answer
                    events.append(ConnectorEvent(kind="text", data={"text": block["text"]}))
            elif block.get("type") == "tool_use":
                events.append(ConnectorEvent(kind="tool_call", data={
                    "id": block.get("id"), "name": block.get("name"), "input": block.get("input")}))
        return events

    def _on_user(self, obj: dict) -> list[ConnectorEvent]:
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        content = message.get("content") if isinstance(message.get("content"), list) else []
        events = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                events.append(ConnectorEvent(kind="tool_result", data={
                    "tool_use_id": block.get("tool_use_id"), "content": _text_of(block.get("content"))[:2000],
                    "truncated": len(_text_of(block.get("content"))) > 2000, "is_error": bool(block.get("is_error"))}))
        return events

    def _on_rate_limit_event(self, obj: dict) -> list[ConnectorEvent]:
        info = obj.get("rate_limit_info")
        if not isinstance(info, dict):
            return []
        self.quota = _quota_of(info)
        return [ConnectorEvent(kind="quota", data=self.quota.model_dump())]

    def _on_result(self, obj: dict) -> list[ConnectorEvent]:
        self.result = obj
        return []

    # ---- the end: success or one of the errors of 3.4 ----------------------------------------------------------------------
    def _error(self, cls: type, message: str = "", **detail: Any) -> ConnectorError:
        detail.setdefault("cli", "claude")
        if self.version:
            detail.setdefault("version", self.version)
        resets_at = detail.pop("resets_at", None)
        return cls(message, provider="claude", detail=detail, resets_at=resets_at)

    def finish(self, exit: ExitInfo) -> TurnResult:
        if exit.reason in ("total_timeout", "idle_timeout"):                      # C22
            which = "idle" if exit.reason == "idle_timeout" else "total"
            seconds = self.plan.idle_timeout_s if which == "idle" else self.plan.timeout_s
            raise self._error(CallTimeoutError, which=which, seconds=seconds)
        if exit.reason == "cancelled":                                            # C23
            raise self._error(CallCancelledError, "stopped")
        if self.result is None:
            raise self._without_result(exit)
        res = self.result
        text = res.get("result") if isinstance(res.get("result"), str) else ""
        failure = self._from_assistant_error(res, text) or self._from_result(res, text, exit)
        if failure is not None:
            raise failure
        structured = res.get("structured_output")
        if self.plan.schema is not None and structured is None:                   # C15, J2 llm.py:170-173
            raise self._error(StructuredError, subtype=res.get("subtype"), present=False)
        if not text.strip() and structured is None:                               # C24
            raise self._error(EmptyReplyError)
        return self._turn_result(res, text, structured)

    def _from_assistant_error(self, res: dict, text: str) -> Optional[ConnectorError]:
        """C4 to C14: `assistant.error` decides before anything else."""
        err = self.assistant_error
        if err is None:
            return None
        shown = (text or self.assistant_text)[:_RESULT_TEXT_CHARS]
        if err == "authentication_failed":
            return self._error(NotSignedInError, shown, reason=err)
        if err in ("oauth_org_not_allowed", "account_on_hold", "verification_required"):
            return self._error(AccountBlockedError, shown, reason=err)
        if err == "rate_limit":
            rejected = self.quota is not None and self.quota.status == "exhausted"
            if rejected or "hit your limit" in (text or self.assistant_text).lower():
                return self._error(QuotaError, shown, reason=err, resets_at=self.quota.resets_at if self.quota else None)
            return self._error(RateLimitedError, shown, reason=err)
        if err == "billing_error":
            return self._error(QuotaError, shown, reason=err)                         # the HealthBook cools it down 15 min
        if err == "overloaded":
            return self._error(OverloadedError, shown, reason=err)
        if err == "server_error":
            return self._error(ServerError, shown, reason=err)
        if err == "invalid_request":
            return self._error(InvalidRequestError, shown or "Claude refused the request as invalid", reason=err)
        if err == "model_not_found":
            return self._error(ModelNotFoundError, shown, model=self.plan.model, reason=err)
        if err == "max_output_tokens":
            return self._error(ReplyTruncatedError, shown, reason=err, partial=self.assistant_text[:2000])
        return None                                       # unknown, cloud_credential_error, ...: the result's fields decide

    def _from_result(self, res: dict, text: str, exit: ExitInfo) -> Optional[ConnectorError]:
        """C15 to C19, then the exit code."""
        subtype = res.get("subtype")
        if subtype == "error_max_structured_output_retries":                      # C15
            return self._error(StructuredError, subtype=subtype, present=res.get("structured_output") is not None)
        if subtype == "error_during_execution":
            errors = res.get("errors") if isinstance(res.get("errors"), list) else []
            said = " ".join(str(e) for e in errors) + " " + exit.stderr_tail
            if _count(res.get("num_turns")) == 0 and "No conversation found" in said:   # C16
                return self._error(SessionLostError, "no conversation found", num_turns=0)
            return self._error(ProviderError, (" ".join(str(e) for e in errors) or text or "error during execution")[:_RESULT_TEXT_CHARS],
                               subtype=subtype)                                          # C17
        if subtype == "error_max_budget_usd":                                      # C18
            return self._error(EnvelopeExceededError, "Claude stopped at the money limit", subtype=subtype)
        if res.get("is_error"):                                                   # C19
            return self._from_status(res, text)
        if isinstance(subtype, str) and subtype != "success":
            return self._error(ProviderError, f"Claude ended with {subtype}", subtype=subtype)
        if exit.returncode != 0:                                                  # a result, then a bad exit
            return self._error(CrashedError, exit=_exit_label(exit), stderr=exit.stderr_tail[-_RESULT_TEXT_CHARS:])
        return None

    def _from_status(self, res: dict, text: str) -> ConnectorError:
        status = res.get("api_error_status")
        status = status if isinstance(status, int) and not isinstance(status, bool) else None
        shown = text[:_RESULT_TEXT_CHARS]
        if status in (401, 403) or any(m in text.lower() for m in _AUTH_MARKERS):
            return self._error(NotSignedInError, shown, status=status)
        if status == 429:
            return self._error(RateLimitedError, shown, status=status)
        if status == 529:
            return self._error(OverloadedError, shown, status=status)
        if status is not None and 500 <= status <= 599:
            return self._error(ServerError, shown, status=status)
        return self._error(ProviderError, shown or "Claude reported an error", status=status, subtype=res.get("subtype"))

    def _without_result(self, exit: ExitInfo) -> ConnectorError:
        """C2, C3, C20, C21: the stream has no `result` line."""
        stderr = exit.stderr_tail
        low = stderr.lower()
        if self.objects == 0 and exit.returncode not in (0, None):
            unknown = re.search(r"unknown option '([^']+)'", stderr)
            if unknown or low.lstrip().startswith("error: unknown option"):       # C2
                return self._error(FlagUnsupportedError, stderr.strip()[:200], flag=unknown.group(1) if unknown else None)
            if "--json-schema is not valid json" in low:                          # C3a
                return self._error(InvalidRequestError, "the JSON schema was refused as not valid JSON", flag="--json-schema")
            if "system prompt file not found" in low:                             # C3b
                return self._error(FlagUnsupportedError, "the system prompt file was not found", flag="--system-prompt-file")
        if "no conversation found" in low:
            return self._error(SessionLostError, "no conversation found")
        if exit.returncode != 0:                                                  # C20: killed by a signal, or a bad exit
            return self._error(CrashedError, exit=_exit_label(exit), stderr=stderr[-_RESULT_TEXT_CHARS:])
        return self._error(ProtocolError, "the stream ended without a result line")   # C21

    def _turn_result(self, res: dict, text: str, structured: Any) -> TurnResult:
        raw = res.get("usage") if isinstance(res.get("usage"), dict) else {}
        out = _count(raw.get("output_tokens"))
        details = raw.get("output_tokens_details") if isinstance(raw.get("output_tokens_details"), dict) else {}
        usage = Usage(input_tokens=_count(raw.get("input_tokens")), cached_input_tokens=_count(raw.get("cache_read_input_tokens")),
                      cache_write_tokens=_count(raw.get("cache_creation_input_tokens")), output_tokens=out,
                      reasoning_tokens=min(out, _count(details.get("thinking_tokens"))))
        total = res.get("total_cost_usd")
        total = float(total) if isinstance(total, (int, float)) and not isinstance(total, bool) and total >= 0 else 0.0
        before = self.plan.cum_usd
        usd = round(total - before if total >= before else total, 10)           # a counter that went backwards is taken whole
        self.cum_usd = total
        self.cum_usage = self.plan.cum_usage + usage
        models = res.get("modelUsage") if isinstance(res.get("modelUsage"), dict) else {}
        model = next(iter(models), None) or self.init_model
        duration = res.get("duration_ms")
        session = res.get("session_id") if isinstance(res.get("session_id"), str) else self.session_id
        return TurnResult(
            text=text, structured=structured, provider="claude", model=model, provider_session_id=session, usage=usage, usd=usd,
            usd_basis="reported", quota=self.quota,
            duration_ms=int(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None,
            subtype=res.get("subtype") if isinstance(res.get("subtype"), str) else None)


def _exit_label(exit: ExitInfo) -> Any:
    return exit.signal_name or exit.returncode


class ClaudeConnector(ModelConnector):
    name = "claude"
    default_model = "sonnet"
    capabilities = Capabilities(native_schema=True, resume=True, images=True, partials=True, mcp=True)

    # ---- model and tools -----------------------------------------------------------------------------------------------------
    def resolve_model(self, requested: Optional[str], *, environ: Optional[Mapping[str, str]] = None) -> str:
        """`SUTRA_CLAUDE_MODEL`, then `CLAUDE_CLI_MODEL` (J2 SETUP.md:94) override the policy's model; default `sonnet`."""
        source = os.environ if environ is None else environ
        for env_name in MODEL_ENV_NAMES:
            if source.get(env_name):
                return super().resolve_model(source[env_name])
        return super().resolve_model(requested)

    def models(self) -> list[ModelInfo]:
        """Aliases only: the CLI has no list command."""
        efforts = ["low", "medium", "high", "xhigh", "max"]
        return [ModelInfo(slug=slug, label=f"{label} (alias)", efforts=efforts, context_window=None, images=True, listed=True)
                for slug, label in (("sonnet", "Sonnet"), ("opus", "Opus"), ("fable", "Fable"))]

    def mcp_servers(self, tools: tuple[str, ...]) -> dict[str, Any]:
        """The MCP entry for a tool profile: the app's own stdlib server, one server for `sutra` and `github` tools. CN-8's
        `tools/profiles.py` can replace this by overriding the method; the server's env holds a path, never a secret."""
        import sutra_app
        root = str(Path(sutra_app.__file__).resolve().parent.parent)
        profile = ",".join(tools)
        return {_MCP_SERVER: {"command": self.cfg.python,
                              "args": ["-m", "sutra_app.connectors.tools.mcp_server", "--profile", profile],
                              "env": {"PYTHONPATH": root, "SUTRA_DB_RO": str(Path(self.cfg.data_dir) / DB_FILENAME)}}}

    # ---- the four hooks --------------------------------------------------------------------------------------------------------
    def build_command(self, plan: TurnPlan) -> Command:
        argv = [self.cfg.claude_exe, "-p", "--output-format", "stream-json", "--verbose", "--model", plan.model,
                "--effort", plan.effort]
        files = ""
        cleanup: list[str] = []
        stdin = plan.prompt
        try:
            if len(plan.system) > SYSTEM_FILE_THRESHOLD and not plan.inline_system:
                files = str(self._private_dir("files"))
                cleanup.append(files)
                path = Path(files) / "system.md"
                write_private_file(path, plan.system)
                argv += ["--system-prompt-file", str(path)]
            else:
                argv += ["--system-prompt", plan.system]
            argv += ["--tools", ",".join(READ_TOOLS) if plan.folder else "", "--strict-mcp-config", "--disable-slash-commands",
                     "--setting-sources", ""]
            if plan.oneshot:
                argv.append("--no-session-persistence")
            elif plan.resume:
                argv += ["--resume", plan.provider_session_id or ""]
            else:
                argv += ["--session-id", plan.provider_session_id or ""]
            if plan.partials:
                argv.append("--include-partial-messages")
            if plan.schema is not None:
                argv += ["--json-schema", json.dumps(plan.schema, ensure_ascii=False, separators=(",", ":"))]
            if plan.images:
                argv += ["--input-format", "stream-json"]
                stdin = self._image_line(plan)
            if plan.tools:
                if not files:
                    files = str(self._private_dir("files"))
                    cleanup.append(files)
                config = Path(files) / "mcp.json"
                write_private_file(config, json.dumps({"mcpServers": self.mcp_servers(plan.tools)}, ensure_ascii=False))
                argv += ["--mcp-config", str(config)]
            if plan.tools or plan.folder:
                allowed = ([*READ_TOOLS] if plan.folder else []) + ([_ALLOWED_TOOLS] if plan.tools else [])
                argv += ["--restricted", "--allowedTools", ",".join(allowed)]
                if plan.folder:
                    argv += ["--disallowedTools", ",".join(_DENIED_TOOLS)]
                argv += ["--permission-mode", "dontAsk", "--permission-prompts", "none"]
            if plan.max_budget_usd is not None:
                argv += ["--max-budget-usd", format(plan.max_budget_usd, ".6f").rstrip("0").rstrip(".") or "0"]
            return Command(argv=tuple(argv), cwd=plan.folder or plan.workdir, env=self._env(), stdin_text=stdin, cleanup=tuple(cleanup),
                           provider="claude")
        except BaseException:
            for path in cleanup:
                shutil.rmtree(path, ignore_errors=True)
            raise

    @staticmethod
    def _image_line(plan: TurnPlan) -> str:
        """stdin for images: ONE json line, the image blocks first and then the text (J2 llm.py:97-106, 153-154)."""
        blocks: list[dict] = []
        for path in plan.images:
            try:
                data = Path(path).read_bytes()
            except OSError as e:
                raise InvalidRequestError(f"image cannot be read: {path} ({e.strerror or e})", provider="claude") from None
            media = next((m for magic, m in _IMAGE_MAGIC if data.startswith(magic)), None)
            if media is None:
                if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                    media = "image/webp"
                else:
                    raise InvalidRequestError(f"not a PNG or JPEG image (or a GIF, WebP or PDF): {path}", provider="claude")
            blocks.append({"type": "document" if media == "application/pdf" else "image", "source": {"type": "base64", "media_type": media,
                                                       "data": base64.b64encode(data).decode("ascii")}})
        blocks.append({"type": "text", "text": plan.prompt})
        return json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}, ensure_ascii=False) + "\n"

    def new_parser(self, plan: TurnPlan) -> ClaudeParser:
        return ClaudeParser(plan, version=self._version)

    def recover(self, plan: TurnPlan, error: ConnectorError) -> Optional[TurnPlan]:
        """C3b: this CLI does not know `--system-prompt-file`; retry ONCE with the text inline."""
        if (error.code == "cli_flag_unsupported" and error.detail.get("flag") == "--system-prompt-file"
                and len(plan.system) > SYSTEM_FILE_THRESHOLD and not plan.inline_system):
            return replace(plan, inline_system=True)
        return None

    def probe_auth(self) -> AuthStatus:
        """`claude auth status`: JSON on stdout, exit 0 or 1, no model call."""
        now = self._clock()
        try:
            info, lines = self._run_probe([self.cfg.claude_exe, "auth", "status"])
        except CliMissingError as e:
            return AuthStatus(provider="claude", installed=False, signed_in=None, detail=e.user_message(), checked_at=now)
        version = self.version()
        doc: Any = None
        try:
            doc = json.loads("\n".join(lines))
        except ValueError:
            pass
        if not isinstance(doc, dict) or not isinstance(doc.get("loggedIn"), bool):
            tail = (info.stderr_tail.strip() or "\n".join(lines).strip() or "no answer")[:200]
            return AuthStatus(provider="claude", installed=True, version=version, signed_in=None,
                              detail=f"claude auth status gave no usable answer (exit {info.returncode}): {tail}", checked_at=now)
        method = doc.get("authMethod") if isinstance(doc.get("authMethod"), str) else None
        lowered = (method or "").lower()
        billing = "api_key" if ("api" in lowered or "console" in lowered) else "subscription" if method else "unknown"
        signed_in = doc["loggedIn"]
        return AuthStatus(
            provider="claude", installed=True, version=version, signed_in=signed_in, method=method, billing=billing,
            plan=doc.get("subscriptionType") if isinstance(doc.get("subscriptionType"), str) else None,
            account=doc.get("email") if isinstance(doc.get("email"), str) else None,
            detail="signed in" if signed_in else "not signed in: run `claude auth login`", checked_at=now)

    def version(self) -> Optional[str]:
        """The CLI's version from `claude --version` ("2.1.308 (Claude Code)"), read once; None when it cannot be read."""
        if self._version is None:
            try:
                _, lines = self._run_probe([self.cfg.claude_exe, "--version"])
            except ConnectorError:
                return None
            found = re.search(r"\d+\.\d+\.\d+\S*", " ".join(lines))
            self._version = found.group(0) if found else None
        return self._version

    def probe_flags(self) -> dict[str, bool]:
        """Feature detection from `--help`, not a version table. `--system-prompt-file` is not listed in the help although it
        works, so it is not probed (C3b handles a CLI without it). Raises CliMissingError when the CLI is not there."""
        _, lines = self._run_probe([self.cfg.claude_exe, "--help"])
        present = set(re.findall(r"--[A-Za-z][A-Za-z0-9-]*", "\n".join(lines)))
        return {flag: flag in present for flag in PROBED_FLAGS}

    def forget_command(self, s: SessionState) -> list[str]:
        return [self.cfg.claude_exe, "purge", "-y", s.workdir]
