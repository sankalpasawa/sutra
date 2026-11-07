# Connectors: the connector layer (router, ModelConnector, Claude, Codex, tool connectors, stub, usage rows)
_Design section · Proposed · 2026-11-04 · merges into `docs/DESIGN.md`. Written against `engine.md` (ENG), `orchestrator.md` (ORCH), `library.md` (LIB), `ui.md` (UI) as they stood at 00:45; `§` = their section numbers (their line numbers still move)._
_Sources: J2 (`J2_Prototype`, cited `file:line`), the Sutra plugin without `sutra-ui`, draw.io page 3, `gen.py`, `docs/DECISIONS.md`, and probes of the real CLIs on 2026-11-04 (`claude` 2.1.308, `codex-cli` 0.146.0). Anything not verified is marked UNVERIFIED._
_Settlements applied 2026-11-04 (`docs/design/settlements/`: S1 contracts, S2 models, S3 web, S4 function nodes). Every paragraph, table row or block they changed carries the settlement id in square brackets, for example `[S1-contracts-02]`, `[S2-models-04]`, `[S3-web-03]`, `[S4-fnodes-07]`. Find them with `grep -n '\[S[1-4]-' docs/design/connectors.md`. Where S4 supersedes a part of S1 to S3, only the S4 text stands._

## 1. Purpose and scope
Every model call in the app goes through this layer (diagram band "Connector layer", `gen.py:159-190`; draw.io page 3 box "AI Provider" and step 3 "claude cli + python models"). One `Router` picks a provider per call from a data table, checks health and quota without a model call, stays inside the allowance a caller sends (v1: none, so only the router's ceiling of 6 invocations per request applies; the caller keeps its envelope) [S1-contracts-06], and runs a `ModelConnector` child: `ClaudeConnector` (`claude -p`, stream-json) or `CodexConnector` (`codex exec --json`), both on the owner's own logins (D7). `StubConnector` answers deterministically for tests and offline. Tool connectors give the CLIs MCP tools. Each step ends in one usage row.
- **In:** `sutra_app/connectors/` (section 2); the two ports other sections call (`engine_port.make_port`, `orchestrator_port.AsyncConnector`); cost normalisation and the usage row the router emits; fake CLIs and captured fixtures; `/api/connectors/*`; the fate of J2's Anthropic-API and Gemini providers (CD1).
- **Out (contracts in 3.10):** the J2 loop, hooks and the `llm.py` shim (ENG §4); the `usage_ledger` table, `UsageStore` and `/api/usage*` (ORCH §3.3, §4.1, ORCH-3); chat sessions and messages (`ChatStore`); org chart; UI pages; the SSE bus; Interface-library models, `transport_schema`, `ReplyParser` (LIB §3.5); installing the CLIs (CD17).
- **Function nodes:** the final spec is `docs/design/function-nodes-spec.json` and its design is `docs/design/function-nodes.md` (S4). Function nodes reach this layer only through the engine's `CallTag` (`function, role, stage, step, atom, purpose`, ENG §4.1). The one thing they ask of it is that every call carries an atom id in `tag.atom` (an atom's id, or an overhead key for a call outside an open turn and for the chat agent); the layer stores what the tag holds and nothing more (3.8, 3.10) [S4-fnodes-07].
- **Platform:** POSIX (macOS, Linux). Windows needs `CREATE_NEW_PROCESS_GROUP` and `taskkill /T`: out of v1 (J2 had Windows notes, `llm.py:117-118`).

### 1.1 Picture
```
engine host (one per run) --complete()----> RouterPort --+
orchestrator (server)     --call_json()---> AsyncConnector -> Router (policy, health, allowance gate, JSON strategy, sessions)
chat panels (server)      --chat_send()------------------->    |-- ClaudeConnector --spawns--> claude -p (stream-json)   [login: this Mac]
                                                              |-- CodexConnector  --spawns--> codex exec --json         [login: ChatGPT]
 UsageSink: UsageStore (server) or EventUsageSink (engine)    |
 <-- one UsageIn per request, built by the Router ------------|-- StubConnector (tests, offline demo)   [S1-contracts-05]
 tool connectors (MCP): Sutra read tools, gh read tools, shown-only Claude-held Gmail/Drive/Slack --> both CLIs
```

### 1.2 What the real CLIs do (probed 2026-11-04; files in `tests/fixtures/connectors/`, listed in `MANIFEST.json`)
Two real calls per CLI (fresh with a schema, then resume). The rest needed no model: signed-out runs use an empty `CLAUDE_CONFIG_DIR` / `CODEX_HOME` (three signed-out Codex runs reached `api.openai.com` and got 401; one `codex login --device-auth` asked for a one-time code that was abandoned), flag errors, `--help`, status commands.
| # | Topic | `claude` 2.1.308 | `codex-cli` 0.146.0 |
|---|---|---|---|
| 1 | Sign-in check, no model call | `claude auth status`: JSON on **stdout**, exit 0 / 1, 0.2-0.5 s: `loggedIn, authMethod "claude.ai", subscriptionType, email, orgName` (`claude/auth_status_*.json`) | `codex login status`: text on **stderr** ("Logged in using ChatGPT" / "Not logged in"), exit 0 / 1, 0.1-0.5 s (`cli_errors.json`). `codex doctor --json` checks local presence only |
| 2 | A call while signed out | fails in 0.9 s: `assistant.error "authentication_failed"`, text "Not logged in · Please run /login", `result.is_error true` but `subtype "success"`, exit 1 (`stream_not_logged_in.jsonl`) | does NOT fail fast: `error` events "Reconnecting... n/5 (unexpected status 401 ...)", websocket then HTTPS fallback, 18-20 s, then `turn.failed`, exit 1 (`exec_not_signed_in.jsonl`) |
| 3 | Success stream | `system/init` → `system/status` → `stream_event`* → `assistant` → `user`(tool_result) → `rate_limit_event` → `result`; first line 1.6 s; one word in 4-5 s | `thread.started` → `turn.started` → `item.completed`(agent_message) → `turn.completed`; one word in 7-8 s at low effort; no text deltas |
| 4 | Structured output | `--json-schema`: `init.tools == ["StructuredOutput"]`, `result.structured_output` (object) and `result.result` (JSON text), `num_turns 2` | `--output-schema <file>`: last `agent_message.text` is the JSON; a bad or missing schema file fails before any event (exit 1, stderr) |
| 5 | Usage and cost | `result.usage` per turn (`input_tokens, cache_creation_input_tokens, cache_read_input_tokens, output_tokens`); `total_cost_usd`; `modelUsage[model].costUSD` with `costBasis "list"` (a list-price estimate: a Max plan is not billed per call); alias `sonnet` ran as `claude-sonnet-5-5` | `turn.completed.usage {input_tokens (includes cached), cached_input_tokens, cache_write_input_tokens, output_tokens, reasoning_output_tokens}`; no cost; a one-word prompt used 12,168 input tokens (fixed prefix) |
| 6 | **Counters are cumulative on resume** | `modelUsage` and `total_cost_usd` are cumulative for the session (call 2: tokens 6 = 2+4, cost 0.019035 = 0.009746 + 0.009289); `result.usage` is per turn | `turn.completed.usage` is cumulative for the thread (24,342 = 12,168 + 12,174); the rollout file holds `total_token_usage` and `last_token_usage` (`rollout_token_count.jsonl`) |
| 7 | Resume | `--session-id <uuid>` on turn 1, `--resume <uuid>` after; same `session_id`, context kept. Unknown id: exit 1, `result.subtype error_during_execution`, `num_turns 0`, stderr "No conversation found with session ID" | `codex exec resume <thread_id> -`. Unknown: exit 1, stderr "no rollout found for thread id ... (code -32600)". Resume takes no `-s` and no `-C`: use `-c sandbox_mode="read-only"` and the process cwd |
| 8 | Quota signals | `rate_limit_event.rate_limit_info {status allowed\|allowed_warning\|rejected, rateLimitType five_hour\|seven_day..., resetsAt, utilization, unifiedWindows}` after every call. `assistant.error` enum (CLI's own schema): authentication_failed, oauth_org_not_allowed, account_on_hold, verification_required, billing_error, rate_limit, overloaded, invalid_request, model_not_found, server_error, unknown, max_output_tokens, cloud_credential_error | nothing in `--json`. The rollout `token_count` carries `rate_limits {primary.used_percent, window_minutes, resets_at, plan_type, rate_limit_reached_type}`. Texts in the binary: "You've hit your usage limit...", "exceeded retry limit, last status:" (wording after it UNVERIFIED) |
| 9 | Cancel | process-group SIGTERM: exit 143 after 2.9 s; SIGINT: exit 0 after 1.3 s; stream-json `control_request {subtype:"interrupt"}` answered `success`; no orphans | killpg SIGTERM ends it and its MCP child; no orphans |
| 10 | MCP | `--mcp-config <file or json> --strict-mcp-config`: `init.mcp_servers [{name,status "connected",source "dynamic"}]`, tools `mcp__<server>__<tool>`. It sends `server/discover` first (answer JSON-RPC -32601), then `initialize` 2025-11-25, `notifications/initialized`, `tools/list`. `--restricted` keeps servers; `--safe-mode` **drops** them. Tool-profile flags accepted (`init.permissionMode "dontAsk"`); a real model tool call is UNVERIFIED | `-c mcp_servers.<n>.command/args/env` defines a server for one invocation (`codex mcp list --json` shows it); it sends `initialize` 2025-06-18, `notifications/initialized`, `tools/list`. `--ignore-user-config --ignore-rules` accepted by `exec` and `exec resume` |
| 11 | Flag errors | unknown option: exit 1, stderr "error: unknown option"; a bad `--effort` is only a **warning**; bad `--json-schema`: exit 1 before any call; `--system-prompt-file` works though absent from `--help` | unknown argument: exit 2, stderr "error: unexpected argument"; bad or missing schema file, missing `-C` dir: exit 1, stderr only |
| 12 | Models | aliases `sonnet`, `opus`, `fable` or full names; no list command | `codex debug models` (0.6 s, no model call): `{models:[{slug, visibility list\|hide, supported_reasoning_levels, context_window, input_modalities}]}`; listed: gpt-5.6-terra, gpt-5.6-luna; the owner's `config.toml` model `gpt-5.4` is not in it |
| 13 | Environment | with only `PATH HOME USER LANG TMPDIR` it finds its login and runs. This shell carries about 30 `CLAUDE_CODE_*` variables, `ANTHROPIC_BASE_URL` and `GITHUB_TOKEN`: J2's denylist (`llm.py:114`) is not enough | the same five variables are enough (login read from `CODEX_HOME`) |
| 14 | Codex sign-in | n/a (detect only) | `codex login --device-auth` prints a link and a one-time code with ANSI colours (`NO_COLOR` ignored) and waits (`login_device_auth.txt`) |
Probe leftovers outside the repo (two small sessions): `claude purge -y /private/tmp/claude-501/-Users-USER-Desktop-development-J2-Prototype/95389736-6ed5-43e7-aee2-f15b087e0ba3/scratchpad/probe/work-claude` and `codex delete 01a1a2b8-6719-7e71-83fa-bcf21c8c1649`.

## 2. Module map
All paths under `~/Desktop/development/sutra-pro/`. Work packages in section 8.
| Path | Responsibility | WP |
|---|---|---|
| `sutra_app/connectors/__init__.py` | exports `Router`, `build_router`, `make_port`, the error classes | CN-1 |
| `…/errors.py` | `ConnectorError` tree on the engine's `ModelError`: `code`, `kind`, `retryable`, `fallback_ok`, `user_message()` | CN-1 |
| `…/models.py` | pydantic: `Message`, `Usage`, `Quota`, `Allowance` (re-exported from `sutra_app.engine.port`, the single definition) [S1-contracts-02], `RouteContext`, `AskRequest`, `JsonRequest`, `TurnResult`, `JsonResult`, `AuthStatus`, `ModelInfo`, `Capabilities`, `SessionSpec`, `SessionState`, `ConnectorEvent`, `ConnectorConfig` | CN-1 |
| `…/env.py` | `PASS_NAMES` (the one allowlist, a tuple of names; the orchestrator's engine launcher imports it) and `child_env(provider, extra)` (built from it minus every `SUTRA_*`, plus the secret-name guard) [S1-contracts-11] | CN-1 |
| `…/process.py` | `ProcessRunner`, `Command`, `ExitInfo`: own process group, stdin writer, line reader, total and idle deadlines, cancel ladder | CN-1 |
| `…/jsonio.py` | `extract_json` and `close_json` are imported from `sutra_app.library.replies` (no copy; the verbatim J2 `llm.py:268-295` code lives there); parse, validate, repair prompt and `prune_nulls` stay here [S2-models-12] | CN-1 |
| `…/schema.py` | `to_json_schema`, `strict_schema` (Codex), `minimal_validate`, `example_from_schema` | CN-1 |
| `…/base.py` | `ModelConnector` ABC and its internals (`TurnPlan`, `LineParser`, `Hooks`, `CallRecord`): sessions, one-shot, JSON strategy | CN-3 |
| `…/claude.py` | `ClaudeConnector` | CN-3 |
| `…/codex.py` | `CodexConnector` (+ device sign-in, model catalog, rollout quota read) | CN-4 |
| `…/stub.py` | `StubConnector`, `ReplyBook` | CN-5 |
| `…/policy.py`, `…/policy.default.json` | `RoutingPolicy` models, loader, `resolve()`; the shipped default | CN-6 |
| `…/health.py` | `HealthBook`: installed, signed-in, cooldown, quota snapshots, TTL caches, breaker | CN-6 |
| `…/usage.py` | `Usage` arithmetic, delta rules, rate card, `UsageIn` (single definition, with `step` and `atom_id`; ORCH and the engine import it) and its builder, the `UsageSink` Protocol (single definition), `MemoryUsageSink`, session-state file [S1-contracts-05] | CN-6 |
| `…/transcript.py` | `render_carry_over(messages)` for a provider switch | CN-7 |
| `…/router.py` | `Router`, `Plan`, `RouterStatus`: plan, health gate, allowance gate, attempts, fallback, JSON strategy, chat sessions, status | CN-7 |
| `…/engine_port.py` | `make_port(spec: PortSpec, *, usage_sink: UsageSink \| None = None) -> ModelPort` (the only definition of `make_port`; `PortSpec` and `Allowance` come from `engine/port.py`), `RouterPort` (ENG §4.1) [S1-contracts-02] | CN-7 |
| `…/orchestrator_port.py` | `AsyncConnector` implementing ORCH's `ConnectorPort` (ORCH §3.5) | CN-7 |
| `…/factory.py` | `build_router(settings, *, usage_sink, events, transcripts, session_hook)`; reads only `data_dir`, `connector` and `offline` from `settings` (ORCH's `Settings` satisfies it) [S1-contracts-08] | CN-9 |
| `…/api.py` | `build_api_router(*, router, write_guard)`: `/api/connectors/*`; `write_guard` is required (`Services.require_token`) [S3-web-03] | CN-9 |
| `…/tools/{__init__,profiles,mcp_server,sutra_tools,github_tools,mediated}.py` | per-CLI tool wiring; stdlib MCP server; read-only Sutra tools; `gh` read tools; shown-only Claude-held connectors | CN-8 |
| `tests/connectors/*.py`, `tests/fakes/{fake_cli.py,claude,codex,gh}`, `tests/fixtures/connectors/**`, `scripts/capture_connector_fixtures.py` | section 7 | CN-1..CN-9 |

## 3. Public interfaces
### 3.1 Shared models (`models.py`; `M` = pydantic `BaseModel` with `extra="forbid"`)
```python
Provider = Literal["claude", "codex", "stub"];  Effort = Literal["low", "medium", "high", "xhigh", "max"]
from sutra_app.engine.port import Allowance      # [S1-contracts-02] re-exported from sutra_app.engine.port (single definition, fields unchanged): what the caller's Priority envelope lets ONE request spend; the caller computes it
#   max_calls: int | None >= 0 (CLI invocations: first try + retries + repairs + fallbacks) · max_usd: float | None >= 0 · deadline: float | None (epoch seconds) · envelope_id: str | None
class RouteContext(M):       # arbitrary_types_allowed
    tag: CallTag = CallTag()                       # sutra_app.engine.port.CallTag: run_id, dept_id, task_id, function (identity, adaptation, priority, coordination, audit, W-<n>, validator, reviewer, summariser, template, chat_agent), role, stage, step (the J2 step number, int, 0 when unknown; never fed from ORCH's string step), call_no, atom (the atom id the call is charged to, or an overhead key), purpose (an open string ^[a-z_]{1,24}$: agent_turn, summary, template, review, plan, judge, change, chat_plan, chat; policy matches stay exact on it) [S1-contracts-07] [S4-fnodes-07]
    session_id: str | None = None; node_id: str | None = None      # chat sessions and graph nodes (ORCH)
    allowance: Allowance = Allowance(); avoid: list[Provider] = []   # avoid: soft, tried last (Audit may pass the writer's provider)
class Message(M): role: Literal["user", "assistant", "system"]; text: str; images: list[str] = []   # PNG paths
class AskRequest(M):         # arbitrary_types_allowed
    system: str = ""; user: str; ctx: RouteContext = RouteContext(); kind: Literal["text", "json"] = "text"; effort: Effort | None = None
    images: list[str] = []; schema: dict | None = None; tools: tuple[str, ...] = (); timeout_s: float | None = None; partials: bool = False
    scripted: Callable[[], str] | None = Field(None, exclude=True)      # J2's `mock`; only the stub calls it
class JsonRequest(AskRequest): schema: type[BaseModel] | dict | None = None; kind: Literal["json"] = "json"
class Usage(M):              # one call, disjoint parts; reasoning is a subset of output
    input_tokens: int = 0; cached_input_tokens: int = 0; cache_write_tokens: int = 0; output_tokens: int = 0; reasoning_tokens: int = 0
    # input_total = input + cached + cache_write (what J2 reports as input_tokens, llm.py:145-147); total = input_total + output
    # __sub__ clamps each part at 0; __add__ sums
class Quota(M): status: Literal["ok", "warning", "exhausted", "unknown"] = "unknown"; window: str | None = None; used: float | None = None
    resets_at: float | None = None; plan: str | None = None; source: Literal["rate_limit_event", "rollout", "error", "none"] = "none"
class TurnResult(M): text: str; structured: Any = None; provider: Provider; model: str | None; provider_session_id: str | None
    usage: Usage; usd: float | None; usd_basis: Literal["reported", "rate_card", "unknown", "none"]; duration_ms: int | None
    quota: Quota | None = None; subtype: str | None = None        # Claude result.subtype, kept for J2's structured record
class JsonResult(M): value: Any; usd: float | None; how: Literal["native", "prompted", "repaired", "stub"]; turn: TurnResult
    calls_made: int; usd_spent: float; def as_tuple(self) -> tuple[Any, float | None, str]      # the diagram's (object, usd, how); usd None = unknown (Codex without rates)
class AuthStatus(M): provider: Provider; installed: bool; version: str | None = None; signed_in: bool | None = None   # None: cannot tell
    method: str | None = None; billing: Literal["subscription", "api_key", "unknown"] = "unknown"; plan: str | None = None
    account: str | None = None      # PII: shown to the local user, never logged
    detail: str = ""; checked_at: float
class ModelInfo(M): slug: str; label: str; efforts: list[Effort]; context_window: int | None; images: bool; listed: bool
class Capabilities(M): native_schema: bool; resume: bool; images: bool; partials: bool; mcp: bool
class SessionSpec(M): session_id: str; provider: Provider | None = None; model: str | None = None; effort: Effort | None = None
    tool_profile: str = "none"; system: str = ""            # validator: session_id fullmatch [A-Za-z0-9_-]{1,64} (it names a directory)
class SessionState(M):       # <work_root>/<session_id>/session.json, atomic write, mode 0600; authoritative for the provider session id: ChatStore.provider_session_id (ORCH §3.4) is a mirror for display, and a missing file means a new provider session with the carry-over [S1-contracts-08]
    session_id: str; provider: Provider; provider_session_id: str | None; model: str; effort: Effort; tool_profile: str = "none"
    workdir: str; turns: int = 0; switches: int = 0; pinned: Provider | None = None; cum_usd: float = 0.0; cum_usage: Usage = Usage(); created_at: float
class ConnectorEvent(M): kind: Literal["started", "text_delta", "text", "tool_call", "tool_result", "quota", "notice", "turn_done"]; data: dict = {}
class ConnectorConfig(M):    # paths and executables; tests point these at the fakes
    data_dir: Path; work_root: Path | None = None            # default <tempdir>/sutra-app-<uid>/work-<key of data_dir>, realpath (CD9)
    claude_exe: str = "claude"; codex_exe: str = "codex"; gh_exe: str = "gh"; python: str = sys.executable
    extra_env: dict[str, str] = {}                            # validator: a name containing KEY, TOKEN, SECRET or PASSWORD is refused
```
### 3.2 Errors (`errors.py`)
`ConnectorError(ModelError)`: the engine's `RuntimeError` subclass (`engine/port.py`, ENG §4.1), so J2's `except RuntimeError` (`j2.py:7095`) and crash path keep working. For the six codes the engine names, the class also subclasses the engine's class (`isinstance(e, NotSignedIn)` holds).
- Attributes: `code` (fine, the engine's vocabulary), `kind` (coarse `unavailable|auth|quota|timeout|bad_output`, what ORCH's adapter reads, ORCH §3.5), `retryable`, `fallback_ok`, `provider`, `detail` (dict, never prompts or secrets; for a failed request it carries the same keys as `UsageIn.detail`, 3.8) [S1-contracts-05], `resets_at`, `user_message()` (plain and actionable; the UI shows it verbatim, UI §6.5).
- `retry` = the router retries up to `max_attempts`; `fallback` = the router may try the next provider.
| code | class | kind | retry | fallback | user message (short) |
|---|---|---|---|---|---|
| `no_model` | `NoProviderError`(`NoModelAvailable`) | unavailable | no | n/a | "No model is available: {why each provider was skipped}" |
| `cli_missing` | `CliMissingError`(`CliMissing`) | unavailable | no | yes | "Claude CLI not found on PATH: install it and run `claude` once" (ENG §6 wording; Codex: `codex login`) |
| `cli_flag_unsupported` | `FlagUnsupportedError` | unavailable | no | yes | "{cli} {version} does not accept `{flag}`: update the CLI" |
| `not_signed_in` | `NotSignedInError`(`NotSignedIn`) | auth | no | yes | "Claude is not signed in: run `claude auth login`" / "Codex is not signed in: use Sign in or run `codex login`" |
| `account_blocked` | `AccountBlockedError` | auth | no | yes | "Your {provider} account needs attention (organisation, hold or verification)" |
| `quota` | `QuotaError`(`QuotaExhausted`) | quota | no | yes | "{provider} usage limit reached; resets {time}" |
| `rate_limited` | `RateLimitedError` | quota | yes | yes | "{provider} is rate limiting; retrying" |
| `overloaded`, `server_error` | `OverloadedError`, `ServerError` | unavailable | yes | yes | "{provider} is busy" / "{provider} had a server error" |
| `timeout` | `CallTimeoutError`(`ModelTimeout`) | timeout | yes | yes | "{provider} did not answer within {n} s" |
| `crashed`, `protocol_error` | `CrashedError`, `ProtocolError` | unavailable | yes, no | yes | "{cli} stopped unexpectedly (exit {n})" / "{cli} gave output this app cannot read" |
| `provider_error`, `model_not_found` | `ProviderError`, `ModelNotFoundError` | unavailable | yes, no | yes | message tail / "model {slug} is not available" |
| `session_lost` | `SessionLostError` | unavailable | no (new session, 3.6) | n/a | internal |
| `empty_reply` | `EmptyReplyError` | bad_output | yes | yes | "{provider} returned nothing" |
| `structured` | `StructuredError`(`StructuredOutputFailed`) | bad_output | no (strategy switch) | no | "the structured reply could not be produced" |
| `invalid_json` | `InvalidJsonError` | bad_output | no | by policy | pydantic or parse errors (first 500 chars) |
| `reply_truncated`, `invalid_request` | `ReplyTruncatedError`, `InvalidRequestError` | bad_output | no | no | "reply was cut off (partial text in detail)" / what was wrong (bad schema, missing image, prompt too long) |
| `envelope_exceeded` | `EnvelopeExceededError` | quota | no | no | "the envelope allows no more calls, money or time" |
| `cancelled`, `policy_invalid` | `CallCancelledError`, `PolicyInvalidError` | unavailable | no | no | "stopped" / the policy file errors |

### 3.3 `ModelConnector` (`base.py`)
```python
class ModelConnector(ABC):
    name: ClassVar[Provider]; capabilities: ClassVar[Capabilities]
    def __init__(self, cfg: ConnectorConfig, runner: ProcessRunner | None = None, clock=time.time): ...
    # sessions (chat nodes): one process per turn; the provider session is a cache of the app's transcript (CD9)
    def start(self, spec: SessionSpec) -> SessionState        # creates the work dir and session.json; no process yet
    def send(self, s: SessionState, m: Message, *, timeout_s: float | None = None, on_event=None) -> TurnResult   # consumes stream()
    def stream(self, s: SessionState, m: Message, *, timeout_s=None, partials: bool = True) -> Iterator[ConnectorEvent]   # last event: turn_done
    def stop(self, s: SessionState) -> bool                   # cancel ladder; False when idle
    def resume(self, ref: SessionState) -> SessionState       # local checks only (work dir, ids); a dead provider session shows at the next send as SessionLostError
    def forget(self, s: SessionState) -> None                 # best effort: `claude purge -y <workdir>` / `codex delete <thread>` (help texts read, not run)
    # health: never a model call
    def auth_status(self, *, refresh: bool = False) -> AuthStatus      # cached 30 s
    def models(self) -> list[ModelInfo]
    def usage(self, s: SessionState | None = None) -> Usage            # session cumulative, or this connector's total since start
    # one-shot
    def call_json(self, prompt: str, tools: Sequence[str] = (), schema: type[BaseModel] | dict | None = None, timeout: float = 900,
                  *, system: str = "", ctx: RouteContext | None = None, effort: Effort | None = None, model: str | None = None) -> tuple[Any, float | None, str]
    def call_text(self, prompt: str, *, system: str = "", images: Sequence[str] = (), tools: Sequence[str] = (), **same) -> TurnResult
    # hooks a child implements
    @abstractmethod def build_command(self, plan: TurnPlan) -> Command           # argv, cwd, env, stdin_text, cleanup paths
    @abstractmethod def new_parser(self, plan: TurnPlan) -> LineParser           # .feed(line) -> [ConnectorEvent]; .finish(exit: ExitInfo) -> TurnResult, or raises ConnectorError
    @abstractmethod def probe_auth(self) -> AuthStatus
    @abstractmethod def probe_flags(self) -> dict[str, bool]                     # reads --help once: feature detection, not a version table
```
- `call_json` on one connector: native schema when `capabilities.native_schema` and the schema JSON is under 100,000 characters, else prompted; a `StructuredError` switches to prompted once; parse or pydantic failures run up to `repair_rounds` repair calls (3.6).
- The connector never builds usage rows: the Router is the only builder, and hands each row to its sink (3.8) [S1-contracts-05]. The base calls `Hooks.before_call(info)` (may raise `EnvelopeExceededError`) and `Hooks.after_call(CallRecord)` around every spawn; direct use outside the Router is for tests only.
- One process per call; a one-shot call runs in a fresh empty temp dir (removed after) with prompt, schema and MCP files at mode 0600, removed in `finally`.
- `max_tokens` is advisory: neither CLI has the flag (J2 `llm.py:110-111`).

### 3.4 `ClaudeConnector` (`claude.py`)
Command line; evidence: fixtures and J2 `llm.py:109-128`.
```
claude -p --output-format stream-json --verbose --model <alias|full> --effort <low|medium|high|xhigh|max>
  [--system-prompt "<text>" | --system-prompt-file <0600 temp file> when len(system) > 20000 (J2 llm.py:117-123)]
  --tools "" --strict-mcp-config --disable-slash-commands --setting-sources ""
  [--no-session-persistence]                       # one-shot calls
  [--session-id <uuid> (turn 1) | --resume <uuid> (turn n)]  [--include-partial-messages]     # chat turns
  [--json-schema '<schema, one line>']             # native structured output, only if under 100,000 characters
  [--input-format stream-json]                     # images: stdin is ONE json line {"type":"user","message":{"role":"user","content":[<image blocks>,<text block>]}} (J2 llm.py:97-106,153-154)
  [--mcp-config <0600 file> --restricted --allowedTools "mcp__sutra__*" --permission-mode dontAsk --permission-prompts none]   # tool profile: flags accepted; a real tool call is UNVERIFIED
  [--max-budget-usd <left>]                        # only with Allowance.max_usd; behaviour UNVERIFIED, the router checks anyway
stdin = the user prompt (never argv) · cwd = a fresh empty temp dir (one-shot) or the session work dir · env = allowlist (CD2)
```
- `effort` is validated before spawning: the CLI only warns on a bad value (1.2 row 11). `--safe-mode` is never used with tools (it drops them).
- The model alias comes from the policy (default `sonnet`, J2 `llm.py:40`); `CLAUDE_CLI_MODEL` (J2 `SETUP.md:94`) and `SUTRA_CLAUDE_MODEL` override it.
- Lines that are not a JSON object are skipped and counted; unknown `type` values are ignored.
| line | becomes |
|---|---|
| `system/init` | `started {session_id, model, tools, mcp_servers}`; a server whose `status != "connected"` adds a `notice` |
| `stream_event` / `content_block_delta` (`text_delta` or `input_json_delta`) | `text_delta` (only with partials) |
| `assistant` (`message.content[]`: `text`, `tool_use`; top-level `error`, `is_api_error_message`) | `text`, `tool_call`; remembers `error` |
| `rate_limit_event` | `quota`, sent to `HealthBook` (`allowed`→ok, `allowed_warning`→warning, `rejected`→exhausted; `resetsAt`, `rateLimitType`, `utilization`) |
| `result` | terminal. `text = result.result`; `structured = result.structured_output`; tokens from `result.usage` (per turn); `usd = max(0, total_cost_usd − session.cum_usd)` then `cum_usd := total_cost_usd` (row 6); model = first key of `modelUsage` (J2 `llm.py:144`); `usd_basis "reported"` |
Error mapping (ids are test ids; first match wins). `is_error` and `subtype` are separate: a failed call can carry `subtype "success"` (row 2). Success needs exit 0 and `is_error == false` (J2 `llm.py:179`).
| id | condition | code | fixture (in `tests/fixtures/connectors/`) |
|---|---|---|---|
| C1 | spawn raises `FileNotFoundError`/`PermissionError`, or `shutil.which` is None | cli_missing | PATH emptied |
| C2 | exit 1, no stdout line, stderr starts "error: unknown option" | cli_flag_unsupported | `cli_errors.json` claude_unknown_option |
| C3 | exit 1, no stdout line, stderr "--json-schema is not valid JSON" → invalid_request; "System prompt file not found" → cli_flag_unsupported (retry once with inline `--system-prompt`) | as listed | `cli_errors.json` claude_invalid_json_schema, claude_system_prompt_file_missing |
| C4 | `assistant.error == authentication_failed` | not_signed_in | `claude/stream_not_logged_in.jsonl` |
| C5 | same, text "Login expired" / "OAuth token revoked" | not_signed_in | `derived/claude_login_expired.jsonl` |
| C6 | `assistant.error` in oauth_org_not_allowed, account_on_hold, verification_required | account_blocked | C4 with the enum edited |
| C7 | `error == rate_limit` and (`rate_limit_event.status == rejected` or text has "hit your limit") | quota (`resets_at` from the event) | `derived/claude_quota_rejected.jsonl` |
| C8 | `error == rate_limit` otherwise, or `api_error_status 429` | rate_limited | C7 without the event |
| C9 | `error == billing_error` | quota (cooldown 15 min) | `derived/claude_billing_error.jsonl` |
| C10 | `error == overloaded` (or status 529) | overloaded | `derived/claude_overloaded.jsonl` |
| C11 | `error == server_error` (or status 5xx) | server_error | `derived/claude_server_error.jsonl` |
| C12 | `error == invalid_request` | invalid_request | `derived/claude_invalid_request.jsonl` |
| C13 | `error == model_not_found` | model_not_found | `derived/claude_model_not_found.jsonl` |
| C14 | `error == max_output_tokens` | reply_truncated | C10 with the enum edited |
| C15 | `result.subtype == error_max_structured_output_retries`, or a schema was sent and `structured_output` is absent (J2 `llm.py:170-173`) | structured | `derived/claude_structured_failed.jsonl` |
| C16 | `result.subtype == error_during_execution`, `num_turns 0`, stderr "No conversation found" | session_lost | `claude/stream_resume_unknown_session.jsonl` |
| C17 | `result.subtype == error_during_execution` otherwise | provider_error | `derived/claude_error_during_execution.jsonl` |
| C18 | `result.subtype == error_max_budget_usd` | envelope_exceeded | C17 with the subtype edited |
| C19 | `result.is_error` without `assistant.error`: status 401/403 or text "Not logged in" / "Please run /login" → not_signed_in; 429 → rate_limited; 5xx → server_error | as listed | edits of the not-logged-in stream |
| C20 | no `result`, killed by a signal or exit ≠ 0 | crashed | `derived/claude_truncated_no_result.jsonl` + exit 137 |
| C21 | no `result`, exit 0 | protocol_error | same, exit 0 |
| C22 | total deadline, or idle deadline (partials only) | timeout (`detail.which`) | fake `hang`, `slow` |
| C23 | `stop()` called | cancelled | fake `slow` |
| C24 | `result` ok but blank text and no structured | empty_reply | `derived/claude_plain_*` with blank text |
| C25 | non-JSON lines between events | ignored, counted | `derived/claude_noise_lines.jsonl` |

### 3.5 `CodexConnector` (`codex.py`)
```
codex exec --json --skip-git-repo-check --ignore-user-config --ignore-rules [--ephemeral]  -s read-only  -C <dir>
  -m <slug> -c model_reasoning_effort="<effort>"  [--output-schema <0600 temp file>]  [-i <png> ...]   -        # prompt on stdin
codex exec resume --json --skip-git-repo-check --ignore-user-config --ignore-rules -m <slug> -c model_reasoning_effort="<effort>" -c sandbox_mode="read-only" [--output-schema <file>] <thread_id> -
  tools:  -c 'mcp_servers.sutra.command="<python>"' -c 'mcp_servers.sutra.args=["-m","sutra_app.connectors.tools.mcp_server","--profile","sutra"]' -c 'mcp_servers.sutra.env={PYTHONPATH="<root>",SUTRA_DB_RO="<db>"}'
```
- `--ephemeral` for one-shot calls. Chat turn 1 omits it and reads `thread_id` from `thread.started`; turn n uses `exec resume` with the process cwd set to the session work dir.
- Sandbox `read-only` (or `workspace-write` if a rule asks). `danger-full-access` and `--dangerously-bypass-*` are never emitted.
- No system-prompt flag: the system text goes first in the prompt as `<system>…</system>` (CD4; `-c developer_instructions` and `model_instructions_file` exist in the binary, UNVERIFIED).
- Images use `-i` (UNVERIFIED live; a failure falls back to Claude by policy, ENG §4.9 asks for "supported or `ModelError`").
- The slug comes from the policy and is checked against `codex debug models` (listed models only, 1 h cache); an unknown slug becomes the first listed model with a `notice`. Effort is clamped to the model's `supported_reasoning_levels`.
- Native schema goes through `strict_schema()` (3.6). It is UNVERIFIED against the real API; a 400 about the schema is X9 and degrades to prompted.
- Parsing: `thread.started` → `started {session_id}`. `item.completed` + `agent_message` → `text` (the reply is the **last** one). Other item types (`command_execution`, `file_change`, `mcp_tool_call`, `web_search`, `todo_list`, `reasoning`, `collab_tool_call` appear in the binary) → `tool_call {type}` only; their fields are UNVERIFIED. `item.completed`+`error` and top-level `error` → `notice`. `turn.completed.usage` is cumulative: delta against `session.cum_usage` (fresh input = `input_tokens − cached_input_tokens`, cached, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`). `turn.failed` → error.
- `usd` = rate card × delta (`usd_basis "rate_card"`) or None (`"unknown"`; the shipped rates are null). After a call the connector reads the last `rate_limits` of that thread's rollout file (`$CODEX_HOME/sessions/**/rollout-*-<thread>.jsonl`) into a `Quota`: best effort, failures ignored, format stability UNVERIFIED.
- `probe_auth` runs `codex login status` (stdout and stderr merged): "ChatGPT" → `billing subscription`; "API key" (wording UNVERIFIED) → `billing api_key`, which the Router refuses with no override (CD13); only a positive `api_key` status is refused, an unknown method is allowed [S1-contracts-17]. `begin_sign_in()` runs `codex login --device-auth`, strips ANSI, returns `{url, code, expires_in 900}` from the first `https://…` line and the `XXXX-XXXXX` code, then polls `login status` every 2 s (5.6).
| id | condition | code | fixture |
|---|---|---|---|
| X1 | spawn fails / not on PATH | cli_missing | PATH emptied |
| X2 | exit 2, stderr "unexpected argument" | cli_flag_unsupported | `cli_errors.json` codex_unknown_argument |
| X3 | exit 1, no event, stderr "Output schema file" / "Failed to read output schema" / "No such file or directory" | invalid_request | `cli_errors.json` codex_output_schema_file_*, codex_missing_working_directory |
| X4 | pre-call `codex login status` exit 1 (no process is started for the call) | not_signed_in | `cli_errors.json` codex_login_status_signed_out |
| X5 | two `error` events with "401" in a row (stop the process: about 3 s instead of 18) or `turn.failed` with "401" / "Unauthorized" / "Missing bearer" | not_signed_in | `codex/exec_not_signed_in.jsonl` |
| X6 | `turn.failed` with "usage limit" (parse "Try again at …" into `resets_at`; else +30 min) | quota | `derived/codex_usage_limit.jsonl` |
| X7 | `turn.failed` with "429" or "Too Many Requests" | rate_limited | `derived/codex_rate_limited_429.jsonl` |
| X8 | `turn.failed` "exceeded retry limit, last status: 5xx" | server_error | `derived/codex_server_error_500.jsonl` |
| X9 | `turn.failed` with "400" and ("schema" or "response_format") | structured | `derived/codex_schema_rejected_400.jsonl` |
| X10 | `turn.failed` with "400" and "model" | model_not_found | `derived/codex_model_unsupported_400.jsonl` |
| X11 | any other `turn.failed` | provider_error | X6 with the message edited |
| X12 | exit 1, stderr "no rollout found for thread id" | session_lost | `cli_errors.json` codex_resume_unknown_thread |
| X13 | no `turn.completed`/`turn.failed`, killed or exit ≠ 0 | crashed | `derived/codex_truncated_no_turn_end.jsonl` + exit 137 |
| X14 | no turn end, exit 0 | protocol_error | same, exit 0 |
| X15 | total deadline | timeout | fake `hang` |
| X16 | `stop()` | cancelled | fake `slow` |
| X17 | `turn.completed` without an `agent_message` | empty_reply | `derived/codex_empty_reply.jsonl` |
| X18 | unknown item types | tolerated (`tool_call`) | `derived/codex_unknown_item_type.jsonl` |

### 3.6 `Router` (`router.py`) and the policy
```python
class Router:
    def __init__(self, connectors: Mapping[Provider, ModelConnector], policy: RoutingPolicy, *, usage_sink: UsageSink | None = None,
                 health: HealthBook | None = None, transcripts: TranscriptSource | None = None, events: Callable[[str, dict], None] | None = None,   # events(type, data) = EventBus.publish_one [S1-contracts-08]
                 session_hook: Callable[[str, Provider, str, str | None], None] | None = None,   # called positionally (session_id, provider, model, provider_session_id) = ChatStore.set_provider(session_id, connector, model, provider_session_id) [S1-contracts-08]
                 sleep=time.sleep, clock=time.time, rng=random.random)
    def plan(self, req: AskRequest) -> Plan                      # pure, no process; raises NoProviderError with the skip reasons
    def complete(self, req: CompletionRequest, on_progress=None) -> CompletionResult   # the engine seam (3.10); never repairs
    def ask(self, req: AskRequest, on_progress=None) -> TurnResult
    def call_json(self, req: JsonRequest, on_progress=None) -> JsonResult
    def chat_start(self, spec: SessionSpec, ctx: RouteContext) -> SessionState
    def chat_send(self, session_id: str, m: Message, ctx: RouteContext, on_event=None) -> TurnResult
    def chat_stream(self, session_id: str, m: Message, ctx: RouteContext) -> Iterator[ConnectorEvent]
    def chat_stop(self, session_id: str) -> bool;  def chat_pin(self, session_id: str, provider: Provider | None) -> None
    def status(self, *, refresh: bool = False) -> RouterStatus   # the shape in section 6; ConnectorPort.status() is its per-provider view
    def close(self) -> None                                      # stops every running child (ModelPort.close)
class TranscriptSource(Protocol): def messages(self, session_id: str, limit: int = 20) -> list[Message]    # implemented by ORCH's ChatTranscripts(chats) (orchestrator/chats.py), not by ChatStore: role agent becomes assistant, only kinds text and question with state ok, the newest `limit` in order [S1-contracts-08]
```
**Plan**
- Rule = first match in `policy.rules` (fnmatch on `function`, `stage`, `role`; exact on `purpose`, `kind`, `has_images`, `tools`) over `defaults`.
- `order` from the rule; providers in `ctx.avoid` go last; a pinned session provider goes first.
- Dropped before any spawn: disabled, not installed, signed out, billing `api_key` (reason "API-key login refused (D7): sign in with your subscription"; Codex status text containing "API key", Claude `authMethod` containing "api" or "console"; no override) [S1-contracts-17], in cooldown or quota `exhausted` before `resets_at`, or lacking a needed capability (images, tools). Each drop is kept as `(provider, reason)`.
- Nothing left → `NoProviderError` with the reasons. The router never falls back to the stub on its own (CD11).
- `SUTRA_CONNECTOR=auto|claude|codex|stub` restricts `order`; `SUTRA_OFFLINE=1` is `stub` (ORCH §6.4).

**Attempts** (per provider, in order)
- Gate (`before_call`): deadline, `Allowance.max_calls`, `max_usd`, and the ceiling `max_calls_per_request` (6). Then the provider semaphore (`max_concurrency`: 4 Claude, 2 Codex). Then the connector call, then `HealthBook.update`.
- A retryable error retries up to `max_attempts` (default 2, J2 `range(2)` at `llm.py:156`) after `retry_delays_s` (2 s, 5 s, plus up to 1 s jitter). Then, if `fallback_ok`, the next provider, with `note` "claude out of quota, answered by codex" and a `{"note": …}` progress event (J2 `llm.py:173,187`). Otherwise the error propagates.
- `invalid_request`, `reply_truncated`, `envelope_exceeded`, `cancelled` never fall back.
- In v1 no caller sends an `Allowance`: the engine keeps J2's own accounting (`calls_used`, `j2.py:6906`; J2 never counted the connector's internal retry either) and sends `allowance=None`, and the chat agent has its own caps (3 attempts per stage, 6 requests per owner message, 120 s per call). The gate is exercised by tests and by future callers (the function-node layer may pass `Allowance(max_calls=3, envelope_id=<atom id>)`). When one is sent it is enforced per request and reported as `calls_made` / `usd_spent`; an over-allowance request raises `EnvelopeExceededError` before any process is spawned. Credits are never converted to usd. The label on the router box is true as: the caller keeps the envelope, the router adds a ceiling of 6 invocations per request (and the call timeout) [S1-contracts-06].

**Health and quota before a call** (no model call; `HealthBook` on the injected clock)
- Installed (`shutil.which`, 60 s) and `auth_status` (30 s; dropped on a `not_signed_in` error).
- Cooldown after errors: quota until `resets_at`, else +15 min (Claude) or +30 min (Codex); `rate_limited` +60 s; `overloaded` +30 s; flag error +10 min. A breaker: 3 `crashed` within 60 s → 60 s.
- `Quota` snapshots from Claude's `rate_limit_event` and Codex's rollout.
- It never reads another program's credentials (CD8). The plugin's `sutra-usage` does (`bin/sutra-usage:20,73`), against ADR-035 §3.

**JSON strategy** (`call_json`; `complete()` with `json_schema` uses step 1 only)
1. Native: Claude `--json-schema`; Codex `--output-schema` of `strict_schema(schema)` (every object `additionalProperties:false`, every property required with optional ones nullable, `default`/`title`/`examples` removed, `$defs` kept; LIB's `transport_schema` already satisfies most of it, LIB §3.5). `prune_nulls` afterwards so a nullable placeholder does not defeat a default.
2. A `structured` error, or a schema over 100,000 characters, switches to prompted: the schema text and "answer with one JSON object only" are added to the prompt. The Router records the sha of a schema whose native call ended in a structured error in `native_blocked` (per process) and starts later calls with that schema prompted, so an unsupported schema costs one failed call per process [S2-models-04].
3. Reply → `extract_json` (fence, brace slice, `close_json` for a cut-off reply; verbatim J2; imported from `sutra_app.library.replies`, the single copy) [S2-models-12] → `model_validate` for a pydantic class (errors as `loc: msg; …`, J2's "Pydantic's own words", `j2.py:8444`) or `minimal_validate` for a dict (type, required keys, primitive property types).
4. On failure up to `repair_rounds` (default 2) stateless repair calls: the original prompt + "YOUR LAST REPLY WAS REJECTED: {errors, 1,500 chars}" + the last reply (3,000 chars) + "Reply again with one JSON object only" (J2's pattern, `j2.py:7086`).
5. Still failing → `InvalidJsonError`. `how` = `native`, `prompted` (first try), `repaired` (needed a round), `stub`.
6. Business rules are never checked here: callers use `ReplyParser` and their own retries (LIB §12 F4; ORCH §5.7 F2 retries three times itself).

**Chat sessions** (state in `<workdir>/session.json`)
- `chat_send` plans (pinned provider first, then policy). If the planned provider differs from `state.provider`, or `provider_session_id` is None, or `session.json` is missing (ChatStore's copy of the id is only a display mirror) [S1-contracts-08], a new provider session starts and the first prompt is `render_carry_over(transcripts.messages(session_id))` + the new message; `switches += 1`, counters reset, `session_hook(session_id, provider, model, provider_session_id)` runs (→ `ChatStore.set_provider`), and `connector.switch` is published.
- A `SessionLostError` (C16, X12) does the same on the same provider. One turn at a time per session (`busy`).
- Carry-over (`transcript.py`): messages up to 60,000 characters (J2 `CHAT_FULL_CHARS`, `j2.py:90`) are rendered whole; above that the last 40 (`CHAT_TAIL`, `j2.py:91`) in full plus one 120-character line per older message, capped at 8,000. Header: "Earlier messages of this conversation, carried over because the provider changed ({a} → {b}); [n earlier messages omitted]". `resume_info` gives at most 20 messages (ORCH §3.4), so the cap rarely bites. No model summary call (cost and a new failure mode).

**Policy** (`policy.py`). A user file `<data_dir>/connectors/policy.json` replaces the packaged `policy.default.json` only if it validates; otherwise `status().policy_error` is set and the default is used. Precedent: models are named only in a versioned data file (plugin `os/routing-policy.json:4`, ADR-038 §4). The default reproduces J2: Claude first, Codex only as fallback.
```json
{"version": 1,
 "providers": {"claude": {"enabled": true, "model": "sonnet", "max_concurrency": 4},
               "codex":  {"enabled": true, "model": "gpt-5.6-luna", "max_concurrency": 2, "sandbox": "read-only"}},
 "defaults": {"order": ["claude", "codex"], "effort_json": "low", "effort_text": "high", "timeout_s": 900, "max_attempts": 2,
              "retry_delays_s": [2, 5], "repair_rounds": 2, "max_calls_per_request": 6, "fallback_on_invalid_json": false,
              "tool_profile": "none", "idle_timeout_s": 120},
 "rules": [{"match": {"function": "chat_agent"}, "timeout_s": 120},
           {"match": {"purpose": "summary"}, "effort": "low", "timeout_s": 300},
           {"match": {"function": "audit", "has_images": true}, "order": ["claude", "codex"]}],
 "rates": {"codex": {"gpt-5.6-luna": {"in_per_mtok": null, "cached_in_per_mtok": null, "out_per_mtok": null}}}}
```
[S1-contracts-17] The key `allow_api_key_billing` no longer exists: an API-key login is refused with no override (Plan above, CD13), and a policy file that still contains the key fails validation.
Effort defaults reproduce J2 (`low` for JSON replies, `high` otherwise, `j2.py:3166`). `idle_timeout_s` applies only to streams with partials: without them a long generation prints nothing after `init`.

### 3.7 `StubConnector` (`stub.py`)
- Deterministic, no process, `how "stub"`, `usd 0.0`, `usd_basis "none"`, tokens = characters / 4.
- Reply resolution: (1) `req.scripted()` (J2's `mock`, `llm.py:73-74`); (2) `ReplyBook` exact `(function, stage)`; (3) `(function, "*")`; (4) `("*", "*")`; (5) built-in: for a schema `example_from_schema(schema)` (required fields, first enum value, `"stub"`, `0`, `False`, `[]`, nested), else `"[stub] "` + the first 60 characters of the prompt.
- With `delay > 0` the text streams in 30 chunks (J2 `_stream_mock`, `llm.py:191-198`, `STUDIO_MOCK_DELAY`).
- `fail_next(code, times=1)` raises any `ConnectorError`, for Router tests. Sessions keep an in-memory transcript. Stub rows carry `provider "stub"`, `model "scripted"`, `ok` true, `usd 0.0`, tokens = characters / 4 and the `atom_id` of the tag like every other row (the engine's `ScriptedPort` builds the same row, which is what lets one assertion set prove the twins, 3.10); readers exclude them from cost totals (the `include_stub=1` query flag shows them) [S1-contracts-02] [S1-contracts-05] [S4-fnodes-07].

### 3.8 Usage row and cost normalisation (`usage.py`)
The table `usage_ledger`, `UsageStore`, `UsageOut` and the read API belong to ORCH (§3.3, §4.1). `UsageIn` and the `UsageSink` Protocol (`record(row) -> int`) are defined here, once, and imported by ORCH and the engine; ORCH keeps only `UsageOut` [S1-contracts-05]. The Router builds exactly one `UsageIn` per request, a failed request included (the diagram's "one record per step", `gen.py:190`), and hands it to a `UsageSink`; nothing else builds usage rows [S1-contracts-05].
| `UsageIn` field | value |
|---|---|
| `provider`, `model` | the provider that answered (the last tried when the request failed); model as reported (`modelUsage` key / slug) |
| `purpose` | `tag.purpose`, or `"chat"` for sessions |
| `session_id`, `node_id`, `task_id`, `dept_id`, `fn` | from `RouteContext` (`fn = tag.function`) |
| `step` | the J2 step label such as `J2.c`, or the builder id such as `W-3`, taken from the tag's step label [S1-contracts-05] |
| `atom_id` | `tag.atom`, the plain id. The server's Projector stores it as given for a function atom and as `<run_id>:<atom id>` for a J2 workflow atom (J2 atom ids restart at `W-1` in every run, S2-models-10); no foreign key, because a usage line can reach the server before its atom line [S1-contracts-05]. The engine host and the chat agent always set it (S4-fnodes-07); the connector layer itself stores NULL for an untagged call [S4-fnodes-07] |
| `tokens_in`, `tokens_out` | sums over attempts of `Usage.input_total` and `output_tokens`. **Tokens are the comparable unit**: known for both providers |
| `usd` | Claude: sum of the reported per-turn deltas (a list-price estimate, row 5). Codex: rate-card estimate if the owner filled `rates`, else NULL (ORCH §7 `test_atoms_usage` expects NULL). Never negative |
| `seconds`, `ok`, `how` | wall time of all attempts; final outcome; `native\|prompted\|repaired\|stub\|chat` |
| `call_ref` | `"{run_id}:{call_no}"` when `tag.call_no > 0` (the engine's `calls.jsonl` id), else `"r:{request_id}"`. The unique index `(task_id, call_ref)` makes re-ingest idempotent |
| `detail` (nullable column `detail_json`, which already exists: A2 accepted) | `request_id`, `attempts[{provider, model, effort, code or "ok", usd, tokens_in, tokens_out, seconds}]`, `cached_in`, `cache_write`, `reasoning`, `usd_basis`, `billing`, `cli_version`, `envelope_id`, `note`; the same keys ride in `CompletionResult.detail` and, for a failed request, in `ConnectorError.detail` [S1-contracts-05] |
- **Delta rules (CD5).** Claude tokens = `result.usage` of the turn; `usd = max(0, total_cost_usd − state.cum_usd)`; `cum_usd := total_cost_usd`. Codex `delta = max(0, turn.usage − state.cum_usage)` per field; `cum_usage := turn.usage`. A one-shot call starts from zero. A counter that goes backwards (new session, CLI change) is taken whole.
- **Example rows from the captured fixtures:** Claude fresh → `tokens_in 3357 (2+1079+2276), tokens_out 53, usd 0.0097459`. The resumed call → `tokens_in 2947, tokens_out 4, usd 0.0092889` (not 0.0190348). Codex fresh → `tokens_in 12168, tokens_out 15, usd NULL`. Resumed → `tokens_in 12174, tokens_out 5`.
- **Who writes: one builder, two sinks, one ledger writer** [S1-contracts-05]. The Router builds the row. In the server process the router gets `usage_sink = UsageStore` and `AsyncConnector.records_usage = True` (ORCH §3.5), so `TurnRunner` and `NodeAsk` do not write their own rows, and the chat agent's calls are counted. In an engine host the router gets `usage_sink=EventUsageSink` (`engine/events.py`, E0), which writes the `usage` event instead of SQLite; the server's Projector turns that line into the same ledger row (ORCH §5.6), so SQLite has one writer (ORCH-D5). The engine's `call_finished` hook is not a usage source: it fires only for `J2Run.call`, so it would miss the summary, template, reviewer, planner and judge calls and every failed request. The mock path never imports this package (`ScriptedPort` builds the same row itself), so `EventUsageSink` takes a `UsageIn` or a plain mapping. The unique `(task_id, call_ref)` index with `ON CONFLICT DO NOTHING` makes a replay harmless. `UsageStore.record` also calls `ChatStore.note_provider` (connector and model only) so a session's provider chip shows the last provider used. A1 is accepted.

### 3.9 Tool connectors (`tools/`)
- **What the CLIs can do.** Claude: `--mcp-config <file> --strict-mcp-config`. Codex: per-call `-c mcp_servers.<name>.*`. Both were verified to start a stdio server and list its tools (1.2 row 10).
- **Profiles** (`tools=("sutra",)` or `("sutra","github")` on `call_json`, or a policy `tool_profile`): `none` (default, J2's plain completion), `sutra`, `sutra+github`. `profiles.py` renders one MCP entry per CLI: a 0600 JSON file for Claude (never on argv), `-c` strings for Codex; the file is deleted in `finally`. The MCP server's own env holds `PYTHONPATH` and `SUTRA_DB_RO` (a path, not a secret) and nothing else.
- **The app's own server** `python -m sutra_app.connectors.tools.mcp_server --profile sutra[,github]`: stdlib only, newline-delimited JSON-RPC 2.0. It answers `server/discover` and any unknown method with error -32601, `initialize` by echoing the client's `protocolVersion` (2025-11-25 and 2025-06-18 were seen), ignores notifications, serves `tools/list`, `tools/call` (result `content:[{type:"text",text:<json>}]`, `isError`) and `ping`; a malformed line gets -32700 and the server keeps running.
- **All tools are read-only (CD14):** the model proposes, the server's write gate disposes (a chart change is a structured reply validated by the library, never a tool).
| tool | returns | source |
|---|---|---|
| `sutra_chart_read(department_id?, depth?)` | the global org chart (sub)tree | `ReadModel.chart` |
| `sutra_models_list()`, `sutra_model_schema(name)` | Interface-library model names; one JSON Schema | `ReadModel.model_names/model_schema` (LIB registry) |
| `sutra_graph_read(workflow_id?)`, `sutra_atom_read(atom_id)` | workflow graph summary; one work atom (goal, task, context) | `ReadModel.graph/atom` |
- `ReadModel` is a Protocol the data-owning sections implement (`--readmodel pkg.mod:factory`). The default opens SQLite as `file:…?mode=ro`, so a write is impossible at the database. `tools/list` shows only the tools the ReadModel supports.
- **GitHub (CD15):** `github_repo_get`, `github_pr_list`, `github_pr_get`, `github_issue_get`, `github_file_get`, implemented by running the owner's `gh api -X GET <fixed template>` (`gh` is installed and signed in here). Its token never enters Sutra's env, argv or config. Arguments: owner and repo `^[A-Za-z0-9_.-]{1,100}$`, numbers are integers, paths without `..`; output cut at 20 KB and wrapped `{"untrusted": true, …}` (plugin charter: provider content is data, never instructions, `connectors/CHARTER.md:20`). Present only if `gh auth status` exits 0.
- **Claude-held Gmail, Drive, Slack (CD16):** shown, not implemented, as in the plugin (`connectors/registry.py:45,109-112`, ADR-035). `tools/mediated.py` returns `{name, via "claude", status added|not_added|unknown, observed_at, note}`. It runs `claude mcp list` only on a manual refresh (it probes every connector and rewrites Claude's cache, ADR-035 M7), at most once per 60 s, single-flight, `stdin=DEVNULL`, explicit cwd, allowlisted env (§7-8). `not_added` only when at least one `claude.ai ` row was parsed (§5), else `unknown`. No account is shown (`account_known: false`, §6). The 2.1.308 output format was NOT captured (the command mutates Claude state, so it was not run); tests use a hand-written sample after ADR-035.

### 3.10 Ports to the other sections
- **Engine (ENG §4.1).**
  - `make_port(spec: PortSpec, *, usage_sink: UsageSink | None = None) -> ModelPort` builds a `Router` over the connectors that the policy and `spec.connector` allow; `spec.mock` or `spec.connector == "stub"` gives a stub-only `Router`. `PortSpec` (`mock`, `connector`, `run_id`, `dept_id`, `task_id`, `data_dir`) and `Allowance` are imported from `sutra_app.engine.port`; `RunSpec` never appears in this package, and `make_port` exists only in `connectors/engine_port.py` [S1-contracts-02]. The engine host decides mock itself (`--mock`, `SUTRA_MOCK`, `SUTRA_OFFLINE`, `STUDIO_MOCK`, or `connector == "stub"`) and then builds J2's `ScriptedPort` without importing this package; otherwise it calls `make_port(PortSpec(mock=False, connector=…, run_id=…, dept_id=…, task_id=…, data_dir=…), usage_sink=EventUsageSink)` and then `port.preflight()` [S1-contracts-02] [S1-contracts-05]. `make_port(PortSpec(mock=True, …))` still returns the stub-only `Router`; one shared assertion set (the engine's `test_engine_port_contract.py`, here `test_engine_port.py`) runs against it and against `ScriptedPort` to prove the twins [S1-contracts-02].
  - `RouterPort.describe()` → `PortInfo(provider, model, mock)` of the first plan. `preflight()` → `PreflightResult(ok, message, providers[{name, installed, signed_in, detail}])` from cached status (a status command runs only when the cache is older than 30 s; no model call). `close()` → `Router.close()`.
  - `complete()` maps `CompletionRequest` → `AskRequest`: `effort` low/high; `json_mode` → kind json; `json_schema` → native; `images` must exist (`InvalidRequestError` if a provider cannot take them); `timeout_s`; `tag` → `RouteContext.tag`; `allowance` (typed `Allowance | None`) → `RouteContext.allowance`, `None` meaning the empty `Allowance()` (the engine sends none in v1, so only the router ceiling applies) [S1-contracts-02] [S1-contracts-06]; `scripted` → stub only; `max_tokens` advisory.
  - The result → `CompletionResult`: `text` stripped (unstripped in stub mode, as J2), `input_tokens = input_total`, `output_tokens`, `usd`, `duration_ms`, `session_id`, `structured {"provider", "subtype", "present"}` when a schema was sent (J2 `llm.py:169`), `note`, `detail` (= `UsageIn.detail`, 3.8) [S1-contracts-05].
  - The router retries once and falls back before it raises; the engine never retries a failed call itself.
- **Orchestrator (ORCH §3.5).** `AsyncConnector(router)` implements `async call_json(prompt, *, schema: dict | None, tools: Sequence[str], timeout: float, function, step, context) -> (dict, float | None, str)` through `asyncio.to_thread(router.call_json, …)`; the tag is built as `step` → `tag.stage`, `function` → `tag.function`, `context.purpose` → `tag.purpose`, `context.task_id` → `tag.task_id`, `context.atom_id` → `tag.atom` (the orchestrator's `TurnRunner` sets it to the request's overhead key on every call of the request) [S4-fnodes-07], and `context.session_id` / `context.node_id` fill `RouteContext.session_id` / `node_id`; it never writes `tag.step`, which stays the J2 step number [S1-contracts-07]; `status()` returns `{provider: {installed, signed_in, detail, …}}`; `records_usage` is True when a `usage_sink` is set; errors carry `.kind`.

## 4. Data
- **No SQL of its own.** `usage_ledger` is ORCH's (3.8). Session state: `<work_root>/<session_id>/session.json` (`SessionState`), mode 0600.
- **Work root** `<tempdir>/sutra-app-<uid>/work-<key>`, `<key>` = the first 12 hex digits of the SHA-256 of the data folder's realpath (two data folders of one user never share session state: the org chat's session id `cs_org` is the same in every data folder), resolved with `realpath` so Claude's per-directory transcript key never changes. It sits outside the repo so no repo `CLAUDE.md` or `AGENTS.md` is picked up. UNVERIFIED which of those the CLIs read in `-p` mode with the flags above; a user-level `~/.claude/CLAUDE.md` would still apply.
- The CLIs keep their own transcripts (`~/.claude/projects`, `~/.codex/sessions`); `forget()` removes them.
- **Policy:** `<data_dir>/connectors/policy.json` (optional) over the packaged default (3.6). `data_dir` is ORCH's `SUTRA_DATA_DIR` (ORCH §4.2).
- **`session.json` example:** `{"session_id":"cs_5e0a77b19c3d","provider":"claude","provider_session_id":"092c7b68-7118-42da-ba0a-57fa2e5ef699","model":"sonnet","effort":"low","tool_profile":"none","workdir":"/private/var/folders/…/sutra-app-501/work/cs_5e0a77b19c3d","turns":2,"switches":0,"pinned":null,"cum_usd":0.0190348,"cum_usage":{"input_tokens":6,"cached_input_tokens":1728,"cache_write_tokens":4570,"output_tokens":57,"reasoning_tokens":0},"created_at":1793748000.0}`
- **Child environment** (`env.py`). Passed (this list is `PASS_NAMES`, a tuple exported by `env.py`) [S1-contracts-11]: `PATH HOME USER LOGNAME LANG LC_ALL LC_CTYPE TMPDIR SSL_CERT_FILE SSL_CERT_DIR HTTPS_PROXY HTTP_PROXY NO_PROXY ALL_PROXY` (and lower-case twins), `XDG_CONFIG_HOME XDG_DATA_HOME XDG_CACHE_HOME XDG_STATE_HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME`. Never passed: any `*API_KEY*`, `*TOKEN*`, `*SECRET*`, `ANTHROPIC_*`, `OPENAI_*`, `CODEX_API_KEY`, `GITHUB_TOKEN`, `CLAUDE_CODE_*`, `CLAUDECODE`, and every `SUTRA_*` (the per-launch write token, D11, must not reach a model CLI). Verified: the allowlist alone runs both CLIs. Gateway or proxy setups pass names through `ConnectorConfig.extra_env`. `PASS_NAMES` is the one allowlist of the project: the orchestrator's launcher of the engine process imports it and adds `SHELL`, `TERM`, `PYTHONPATH` (worktree runs), every `SUTRA_*` except `SUTRA_TOKEN`, and the seven task-settings keys, so an engine host hands its CLI children the same login directories and proxy and certificate settings; `child_env` then drops every `SUTRA_*` again for the CLIs. No name in `PASS_NAMES` matches `KEY`, `TOKEN`, `SECRET` or `PASSWORD` (a test) [S1-contracts-11].

## 5. Flows
**5.1 One-shot structured call** (chat agent step 3, ORCH §5.2 T4; engine builders)
1. Caller → `Router.call_json` / `complete`. 2. `plan`: rule, order, health drops. 3. First choice: gate, semaphore, fresh temp dir, `schema.json` written for Codex. 4. The connector spawns the CLI (prompt on stdin), reads lines, emits progress. 5. Parse and validate (3.6). 6. Success: `HealthBook.ok`, one `UsageIn`, the result with a `note` if a fallback happened. 7. Temp dir and files removed in `finally`.

**5.2 Chat turn**
1. `chat_send`. 2. Load `session.json`. 3. Plan with the pinned provider first. 4. Same provider and live id: `--resume` / `exec resume`; else 5.3. 5. Stream events to the caller (`text_delta`, `tool_call`, `quota`). 6. `turn_done`: delta usage, update `session.json`, `session_hook` if the provider id changed, one `UsageIn` (`how "chat"`).

**5.3 Switch or lost session**
1. Planned provider ≠ stored provider, or `SessionLostError`. 2. New provider session; the work dir stays. 3. First prompt = carry-over + message. 4. `switches += 1`, counters reset, `session_hook`, `connector.switch`. 5. The old provider session is `forget()`-ed in the background (best effort).

**5.4 Failures** (each has a test)
- **Model call fails** (overloaded, server error): retry after 2 s, then 5 s, then fallback with a note. All fail → the last error propagates (engine: the run stops "Stopped: …", ENG §6; orchestrator: F1/F2, ORCH §5.7).
- **CLI missing:** C1/X1 at plan time → skipped with the install hint; the only provider → `NoProviderError` with the `cli_missing` text.
- **Not signed in:** `auth_status` says so before any call (Codex would waste 18 s); fallback or the error text.
- **Quota:** cooldown to `resets_at`; fallback; the next call skips the provider without spawning.
- **Child crashes or is killed:** C20/X13 → `crashed`, one retry, fallback. `Router.close()` (the host calls it on stop and SIGTERM) kills running children first. Children run in their own session, so a host killed with SIGKILL leaves at most the CLIs it had running; they end when the model answers or on their next write to the closed pipe.
- **Invalid JSON:** repair rounds, then `InvalidJsonError`.
- **Timeout:** the cancel ladder (SIGINT, 5 s, SIGTERM, 5 s, SIGKILL; Claude exited in 1.3 s and 2.9 s) and the call counts as `timeout`.
- **Envelope:** when a caller sends an `Allowance` (v1: tests and future callers; the engine keeps J2's own accounting, where Priority decides hold or approval, `j2.py:6919-6938`), `EnvelopeExceededError` is raised before spawning and the caller decides [S1-contracts-06].
- **Cancel:** `stop()` / `chat_stop`.

**5.5 Start-up.** `build_router` loads the policy, creates the connectors, applies `settings.connector` and `settings.offline` (ORCH §6.4 resolves them from `SUTRA_CONNECTOR` / `SUTRA_OFFLINE`; with `data_dir` they are the only settings fields it reads) [S1-contracts-08], probes `--help` flags once per CLI (a missing required flag marks the provider `degraded`) and warns when a CLI version differs from the tested ones (2.1.308, 0.146.0).
**5.6 Codex sign-in.** `POST …/codex/sign-in` → `begin_sign_in()` starts the device flow and returns link, code, expiry; the UI shows them; `GET …/sign-in/{id}` polls `login status`; `DELETE` stops the process; success clears `signed_out` and publishes `connector.health`.

## 6. Endpoints and events
Router `build_api_router(*, router, write_guard)`; `write_guard` is `Services.require_token` (ORCH 6.1: header `X-Sutra-Token` only, no cookie), a required keyword argument [S3-web-03] [S1-contracts-08]. ORCH-8 mounts it with `app.include_router(build_api_router(router=router, write_guard=require_token))`; the router carries the `/api/connectors` prefix [S1-contracts-08]. The UI today shows Connectors read-only from `GET /api/health` (UI §6.6, §8); these routes add the controls and the detail: UI-7 adds a Test button per provider and, for Codex only, Sign in, showing the server's `user_message()`; there is no pin control in v1 [S1-contracts-08]. Routes that stay with their owners: `/api/health` (uses `status()`), `/api/usage*`, `/api/engine/settings` [S1-contracts-08].
| Route | Request → response |
|---|---|
| `GET /api/connectors/status?refresh=0` | `{"mode":"live\|offline","policy":{"version":1,"source":"default\|file","error":null},"providers":[{"name":"claude","installed":true,"version":"2.1.308","signed_in":true,"method":"claude.ai","billing":"subscription","plan":"max","account":"user@example.com","health":{"state":"ok","until":null,"reason":null},"quota":{"status":"ok","window":"five_hour","used":0.09,"resets_at":1793748600,"source":"rate_limit_event"},"models":[{"slug":"sonnet","label":"Sonnet (alias)"}],"today":{"calls":12,"tokens":48210,"usd":0.31}}, {"name":"codex",…}],"tools":{"sutra":true,"github":false},"mediated":"/api/connectors/mediated"}` |
| (GAP-providers, as built) | each provider also has `plan_label` ("Claude Max", "ChatGPT Go"), and `quota` gains `windows` (every usage window: `[{key, label, used, resets_at}]`, from Claude's `unifiedWindows` and Codex's primary and secondary) and `seen_at`; the last snapshot is kept in `<data>/connectors/quota.json` (0600) and read back at start, so an exhausted one still blocks until its reset. `/api/health` carries the same `health` object and `quota` per provider (never `account`, CN-7) |
| `GET /api/connectors/models?provider=codex` | `{"models":[ModelInfo…]}` |
| `GET /api/connectors/policy` · `PUT` (guard) | the policy JSON · validated body → stored and returned; 422 with the error envelope (`code policy_invalid`, `details.errors` lists the problems) [S3-web-15] |
| `POST /api/connectors/{provider}/test` (guard) | one tiny call ("Reply with the single word ok") → `{"ok":true,"seconds":4.8,"tokens_in":…,"usd":…}` or the error envelope (`details.kind` holds the kind) [S3-web-15]; refused in offline mode |
| `POST /api/connectors/codex/sign-in` (guard) · `GET …/sign-in/{id}` · `DELETE …/sign-in/{id}` (guard) [S3-web-03] | `{"id","url","code","expires_in":900}` · `{"state":"pending\|signed_in\|failed\|expired"}` · 204 |
| `PUT /api/connectors/sessions/{session_id}/provider` (guard) | `{"provider":"codex"\|null}` pins the chat's provider (the next send switches, 5.3) → 204; no UI control in v1 [S1-contracts-08] |
| `PUT /api/connectors/{provider}/path` (guard; GAP-providers) | `{"path":"/full/path/to/claude"\|null}`: the CLI file the owner chose in Settings, checked (a full path to an executable file named as the command) and kept in `<data>/connectors/bins.json`, followed at once by the running router → `{"provider","path","installed","signed_in","detail"}`; a refused file is the 422 envelope with the reason; refused offline (409) |
| `GET /api/connectors/tools` | `{"profiles":["none","sutra","sutra+github"],"tools":[{name,description,read_only:true}]}` |
| `GET /api/connectors/mediated` · `POST …/refresh` (guard) | `{"truth_class":"observed","account_known":false,"items":[{name,via:"claude",status,observed_at,note}]}`; refresh answers 429 inside 60 s |
- Errors: the orchestrator envelope `{error: {code, message, details: {kind}}}` (ORCH 6.1); `message` is the user sentence [S3-web-15].
- **Events** (through the orchestrator `EventBus` callback, which lists them in ORCH 6.3; topic prefix `connector`) [S3-web-06]: `connector.health {provider, state, until, reason}`, `connector.switch {session_id, from, to, reason}`, `connector.mode {mode}`. Usage events stay `usage.recorded` (ORCH).

## 7. Tests
The default suite calls no real model. Fakes replay the captured streams; live tests carry `@pytest.mark.live` and run only with `SUTRA_LIVE=1`. Run: `scripts/py -m pytest tests/connectors -q`.
**Cross-section contract tests** that import this package (the `make_port` signature and the `ScriptedPort` twin, the usage round trip, the env allowlist, the identity of the JSON extractors) live in `tests/contracts/` (CT-1, merged after CN-7 and CN-9) [S1-contracts-02] [S1-contracts-05] [S1-contracts-11] [S1-contracts-18].
**Fake CLIs.** `tests/fakes/{claude,codex,gh}` are two-line `sh` wrappers that run `tests/fakes/fake_cli.py <name> "$@"` (stdlib; python from `SUTRA_FAKE_PYTHON`).
- Env: `FAKE_CLI_SEQUENCE` (comma list of scenarios, one per invocation, the last repeats; the counter lives in `FAKE_CLI_STATE`), `FAKE_CLAUDE_AUTH` / `FAKE_CODEX_AUTH` (`signed_in|signed_out`), `FAKE_REPLY_JSON` / `FAKE_REPLY_TEXT` (replace the reply in `structured_output`, `result`, the tool_use input, `agent_message.text`), `FAKE_COST_USD`, `FAKE_USAGE`.
- Scenario = a fixture name (`ok_structured`, `ok_plain`, `not_logged_in`, `quota`, `overloaded`, … one per file in the manifest) or: `hang` (sleeps; honours SIGINT and SIGTERM), `slow` (a line every 0.3 s, then finishes), `slow401` (two 401 error events 0.5 s apart, then keeps going), `crash` (partial stream, exit 137), `noise`, `bad_flag`.
- It rewrites `session_id` / `thread_id` to the id given in `--session-id` / `--resume`, keeps cumulative counters per session in `FAKE_CLI_STATE/sessions.json` (reproduces row 6), answers `auth status`, `login status`, `debug models`, `--version`, `--help`, `mcp list`, `login --device-auth`, and appends `{cli, argv, cwd, stdin, env_keys}` to `FAKE_CLI_STATE/calls.jsonl`.
| File | Asserts |
|---|---|
| `test_errors.py` | every code in 3.2 has the table's flags; classes are `RuntimeError` and the engine's classes where named; `kind` set; `as_dict` holds no prompt text |
| `test_models.py` | `Usage` subtraction clamps; `input_total`; `extra="forbid"`; `Allowance` is the engine's class object (re-export; bounds as in `engine/port.py`) [S1-contracts-02]; `extra_env` refuses secret names; `SessionSpec` id pattern; `JsonResult.as_tuple` |
| `test_env_process.py` | allowlist drops `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GITHUB_TOKEN`, `CLAUDE_CODE_*`, `SUTRA_*`, keeps `PATH`, `HOME`; `PASS_NAMES` contains `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and no name matching `KEY`, `TOKEN`, `SECRET` or `PASSWORD`, and `child_env` is built from it [S1-contracts-11]; 1 MB stdin does not deadlock; stderr tail capped; total and idle deadlines; cancel ladder order against a child that ignores SIGINT; a grandchild dies with the group; noise lines pass |
| `test_jsonio.py` | `extract_json` and `close_json` here are the library's objects (`is`); the verbatim J2 cases (`llm.py:268-295`: fence, brace slice, cut-off reply, no object) are tested once, in `tests/library/test_lib_replies.py`; here: the parse and validate paths, repair prompt caps, `prune_nulls` [S2-models-12] |
| `test_schema.py` | `strict_schema`: all required, optionals nullable, `additionalProperties:false` everywhere, `default` removed, `$defs` kept, idempotent; `minimal_validate`; `example_from_schema` validates against its model; the 100,000-char gate |
| `test_fakes.py` | each scenario replays its fixture; sequence advance; cumulative counters on resume; the call log |
| `test_claude_parse.py` | each Claude fixture line by line: event order; structured fixture → object, usage, usd 0.0097459, quota ok; resume fixture with `cum_usd 0.0097459` → usd 0.0092889; MCP fixture lists `sutra`; noise skipped |
| `test_claude_connector.py` | exact argv for six shapes (one-shot text, one-shot native schema, chat turn 1, turn 2, tools, images) as golden lists; stdin; env keys; cwd; a 20,001-char system prompt → 0600 file, deleted; `--max-budget-usd` only with an allowance; bad effort refused before spawn; start / send / resume / stop; `stop()` during `slow` returns within 12 s with no process left; `forget` argv |
| `test_claude_errors.py` | one parametrised case per row C1-C25, rows read from the code table `CLAUDE_ERROR_MAP`; a meta-test checks every id has a case |
| `test_codex_parse.py`, `test_codex_connector.py` | fixtures; delta usage 12,174 / 10,368 cached / 5; argv goldens for exec, resume, tools, schema (file content asserted); prompt `-` on stdin; `slow401` ends in under 5 s; `login status` pre-check; rollout quota read and its failure ignored; `begin_sign_in` parses `login_device_auth.txt` (ANSI stripped); `models()` lists only `visibility list`; unknown slug replaced; effort clamped; an `api_key` status makes the provider unavailable with the reason "API-key login refused (D7): sign in with your subscription" [S1-contracts-17] |
| `test_codex_errors.py` | one case per row X1-X18, with the same meta-test |
| `test_stub.py` | same input twice → same output; resolution order including `scripted`; schema example validates; `fail_next`; chunking and delay; token estimate |
| `test_policy.py` | default loads; first match wins; fnmatch; bad provider → `PolicyInvalidError`; invalid user file → default plus `policy_error`; J2 effort defaults; `allow_api_key_billing` is absent from the shipped default and a policy file containing it fails validation [S1-contracts-17] |
| `test_health.py` | TTLs on a fake clock; every error's cooldown; rejected quota skips until `resets_at`; breaker; recovery |
| `test_usage.py` | delta rules for both CLIs including a counter going backwards; `UsageIn` fields (now with `step` and `atom_id`) and the four example rows; `call_ref` (`{run_id}:{call_no}`, else `r:{request_id}`); the `detail` keys and `detail.attempts`; a failed request builds a row with `ok` false; a row reaches the sink exactly once per request; `atom_id` is `tag.atom`, and None for an untagged call; null rate card → usd None [S1-contracts-05] [S4-fnodes-07] |
| `test_transcript.py` | whole under 60,000; tail 40 plus digest above; header; deterministic |
| `test_router_plan.py` | order by rule; `avoid`; every skip reason; `NoProviderError` text; capability filter; `SUTRA_CONNECTOR` / `SUTRA_OFFLINE` |
| `test_router_attempts.py` | retry sleeps `[2,5]` (fake sleep); fallback on quota and not on `invalid_request`; one `UsageIn` per request with attempts in `detail`; the semaphore caps concurrency; `note` text |
| `test_router_gate.py` | `max_calls` 1 with a transient failure → `EnvelopeExceededError`, no second spawn; `max_usd`; `deadline`; repairs count; `calls_made` / `usd_spent`; ceiling 6 |
| `test_router_json.py` | native; `structured` → prompted; not-JSON → repair → success (`how repaired`, 2 spawns); never valid → `InvalidJsonError`; pydantic instance returned; Codex schema file content; wrong shape; cut-off JSON closed; `test_native_blocklist`: a schema whose native call ended in a `structured` error is recorded in `native_blocked` and the next call with it starts prompted (one failed call per process) [S2-models-04] |
| `test_router_chat.py` | three turns keep ids and sum usage correctly; a switch on quota injects the carry-over into stdin and calls `session_hook`; lost session (C16, X12) restarts; `busy` rejects a second send; pin; stop |
| `test_engine_port.py` | `CompletionRequest` → result mapping field by field; stub honours `scripted`; errors are the engine's classes; `describe` / `preflight` / `close`; the same assertions as ENG's `ScriptedPort` contract test; `inspect.signature(make_port)` has exactly the parameters `spec: PortSpec` and keyword-only `usage_sink` with default `None` (3.10), `PortSpec` and `Allowance` import from `sutra_app.engine.port`, `make_port(PortSpec(mock=True, …))` is a stub-only `Router`, `allowance=None` becomes the empty `Allowance()` [S1-contracts-02] |
| `test_orchestrator_port.py` | `call_json` signature, `(dict, usd, how)`, `.kind` values, `status()` shape, `records_usage`, the sink receives `purpose` / `session_id`; the tag built for `call_json(function='chat_agent', step='decide', context={'purpose': 'chat_plan', 'session_id': 'cs_org', 'node_id': 'root'})` equals `CallTag(function='chat_agent', stage='decide', purpose='chat_plan')` with `RouteContext.session_id` `'cs_org'` [S1-contracts-07]; adding `'atom_id': K` to the context gives `tag.atom == K` and the row the sink receives has `atom_id == K`, and `tag.step` stays 0 [S4-fnodes-07] |
| `test_tools_mcp.py` | the server as a subprocess: `server/discover` → -32601, `initialize`, `tools/list`, `tools/call`, unknown method, notification, malformed line; read-only DB (a WAL-mode database) rejects writes; profile renders the Claude file (0600, deleted) and Codex `-c` strings as goldens; `mcp/*.jsonl` replay as client scripts |
| `test_tools_github.py` | with the fake `gh`: argument validation, truncation, `untrusted` wrapper, absent when `gh auth status` fails, no token env |
| `test_mediated.py` | parser on the hand-written sample; `not_added` only with proof of presence; 60 s limit and single flight; env / stdin / cwd |
| `test_factory.py` | auto mode with fakes signed in and out; `SUTRA_OFFLINE`; policy error surfaced; flags probe marks `degraded`; `build_router` needs only `data_dir`, `connector` and `offline` from `settings` [S1-contracts-08] |
| `test_api.py` | status shape; policy PUT 422 and persist; building the router without `write_guard` raises `TypeError`, and every PUT/POST/DELETE route has `write_guard` in its dependency tree [S3-web-03]; every error body has the shape `{error: {code, message, details}}` [S3-web-15]; sign-in start and poll with the fake Codex; test endpoint; pin |
| `test_live.py` (`live`) | at most two tiny calls per CLI: round trip; native schema; Codex strict-schema acceptance; usage delta ≥ 0 on resume; one MCP tool call each (closes the UNVERIFIED items) |

## 8. Work packages
Branch per package (`scripts/wt.sh`); merge gate `scripts/gate.sh`. No two packages own the same path; each package also owns its hand-over note `docs/notes/<WP>.md` (a rule of `scripts/plan_tools.py`). Acceptance uses `scripts/py`.
| WP | Title | Owns | Depends | Acceptance |
|---|---|---|---|---|
| CN-1 | Foundations (`env.PASS_NAMES` exported [S1-contracts-11]; JSON helpers imported from the library [S2-models-12]) | `sutra_app/connectors/{__init__,errors,models,env,process,jsonio,schema}.py`; `tests/connectors/{test_errors,test_models,test_env_process,test_jsonio,test_schema}.py` | E0 (`engine/port.py`), L1 (`library/replies.py`) [S2-models-12] | `scripts/py -m pytest tests/connectors/test_errors.py tests/connectors/test_models.py tests/connectors/test_env_process.py tests/connectors/test_jsonio.py tests/connectors/test_schema.py -q`; `scripts/py -m pytest tests/connectors/test_env_process.py -q` [S1-contracts-11] |
| CN-2 | Fakes and fixtures | `tests/fakes/*`; `tests/connectors/{conftest,test_fakes}.py`; `tests/fixtures/connectors/**`; `scripts/capture_connector_fixtures.py` | none | `scripts/py -m pytest tests/connectors/test_fakes.py -q` |
| CN-3 | Base and Claude | `sutra_app/connectors/{base,claude}.py`; `tests/connectors/{test_claude_parse,test_claude_connector,test_claude_errors}.py` | CN-1, CN-2 | `scripts/py -m pytest tests/connectors/test_claude_parse.py tests/connectors/test_claude_connector.py tests/connectors/test_claude_errors.py -q` |
| CN-4 | Codex (an API-key login is refused in `probe_auth`) [S1-contracts-17] | `sutra_app/connectors/codex.py`; `tests/connectors/{test_codex_parse,test_codex_connector,test_codex_errors}.py` | CN-3 | `scripts/py -m pytest tests/connectors/test_codex_parse.py tests/connectors/test_codex_connector.py tests/connectors/test_codex_errors.py -q`; `scripts/py -m pytest tests/connectors/test_codex_connector.py -q` [S1-contracts-17] |
| CN-5 | Stub | `sutra_app/connectors/stub.py`; `tests/connectors/test_stub.py` | CN-3 | `scripts/py -m pytest tests/connectors/test_stub.py -q` |
| CN-6 | Policy (no `allow_api_key_billing`) [S1-contracts-17], health, usage (`UsageIn` with `step` and `atom_id`) [S1-contracts-05] | `sutra_app/connectors/{policy.py,policy.default.json,health.py,usage.py}`; `tests/connectors/{test_policy,test_health,test_usage}.py` | CN-1 | `scripts/py -m pytest tests/connectors/test_policy.py tests/connectors/test_health.py tests/connectors/test_usage.py -q`; `scripts/py -m pytest tests/connectors/test_usage.py -q` [S1-contracts-05]; `scripts/py -m pytest tests/connectors/test_policy.py -q` [S1-contracts-17] |
| CN-7 | Router and ports (`make_port(spec: PortSpec, *, usage_sink: UsageSink \| None = None) -> ModelPort` [S1-contracts-02]; `AsyncConnector` tag mapping, with `context.atom_id` → `CallTag.atom` [S1-contracts-07] [S4-fnodes-07]) | `sutra_app/connectors/{transcript,router,engine_port,orchestrator_port}.py`; `tests/connectors/{test_transcript,test_router_plan,test_router_attempts,test_router_gate,test_router_json,test_router_chat,test_engine_port,test_orchestrator_port}.py` | CN-4, CN-5, CN-6 | `scripts/py -m pytest tests/connectors/test_transcript.py tests/connectors/test_router_plan.py tests/connectors/test_router_attempts.py tests/connectors/test_router_gate.py tests/connectors/test_router_json.py tests/connectors/test_router_chat.py tests/connectors/test_engine_port.py tests/connectors/test_orchestrator_port.py -q`; `scripts/py -m pytest tests/connectors/test_engine_port.py -q` [S1-contracts-02]; `scripts/py -m pytest tests/connectors/test_orchestrator_port.py -q` [S1-contracts-07] [S4-fnodes-07] |
| CN-8 | Tool connectors | `sutra_app/connectors/tools/*`; `tests/connectors/{test_tools_mcp,test_tools_github,test_mediated}.py` | CN-1, CN-2 | `scripts/py -m pytest tests/connectors/test_tools_mcp.py tests/connectors/test_tools_github.py tests/connectors/test_mediated.py -q` |
| CN-9 | Factory, HTTP API (required `write_guard`, ORCH error envelope) and live tests [S3-web-03] [S3-web-15] | `sutra_app/connectors/{factory,api}.py`; `tests/connectors/{test_factory,test_api,test_live}.py` | CN-7, CN-8 | `scripts/py -m pytest tests/connectors/test_factory.py tests/connectors/test_api.py -q`, then `scripts/py -m pytest tests/connectors -q` (all, no live); live: `SUTRA_LIVE=1 scripts/py -m pytest tests/connectors/test_live.py -q -m live` |
Order: CN-2 can start at once and CN-1 as soon as E0 and L1 are merged (CN-1 imports `engine/port.py` and `library/replies.py`) [S2-models-12]; then CN-3; then CN-4, CN-5, CN-6, CN-8 in parallel; CN-7; CN-9. Risky first: CN-1 (`process.py` cancel ladder) and CN-3 (cumulative-delta logic) carry the facts that bite.

## 9. Decision proposals and the architecture diagram
Provisional ids `CD<n>`; the consolidator assigns final `D<n>` (other sections already use D13-D22). Respected: D7, D8, D9, D11. **Agreements with the other sections** (all four accepted by S1):
- **A1 engine (accepted) [S1-contracts-02] [S1-contracts-05]:** `CompletionRequest.allowance: Allowance | None` and `CompletionResult.detail`; engine hosts use `usage_sink=EventUsageSink` and the `usage` event (3.8).
- **A2 orchestrator (accepted with `ChatTranscripts`, `note_provider`, `publish_one`) [S1-contracts-08]:** nullable `detail_json` on `usage_ledger` (it exists) and `UsageIn.detail` [S1-contracts-05]; read `.kind`; mount `build_api_router` with `write_guard=Services.require_token` [S3-web-03]; wire `ChatStore.set_provider` as the positional `session_hook` and ORCH's `ChatTranscripts(chats)` as `TranscriptSource` (3.6).
- **A3 library (accepted) [S1-contracts-08]:** schemas come from `transport_schema`; `ReplyParser` stays the caller's.
- **A4 UI (narrowed) [S1-contracts-08]:** a Test button per provider and, for Codex only, Sign in, in the Connectors settings rows (section 6); no pin control in v1.

Decisions (what, why, rejected, diagram):
- **CD1 Confirm D7: J2's Anthropic-API and Gemini providers are not carried over.** Why: the diagram's connector layer is two CLI children; a direct API call has no subprocess boundary, no replay and no per-step timeout (plugin ADR-005 `:17`); an API key bills the API (D7); the Gemini path (`llm.py:207-261`) is built around free-tier pacing (`SETUP.md:62`). Kept as ideas: fallback across models on 404/429/500/503 (→ Router fallback), `LAST_META` (→ `CompletionResult`), one retry (→ `max_attempts 2`). Another provider is a subclass implementing four hooks. Rejected: keeping them behind a flag (untestable without keys, against D7). Diagram: ModelConnector note "API-key providers dropped".
- **CD2 One subprocess per call, own process group, environment allowlist, prompt on stdin, explicit cwd.** Why: the shell here carries `CLAUDE_CODE_*`, `GITHUB_TOKEN` and a base URL; ADR-035 §8 chose an allowlist; the probes ran on it. Rejected: J2's denylist (`llm.py:114`); prompts on argv. Diagram: badge on ModelConnector.
- **CD3 Claude: always `stream-json --verbose`; the `result` line decides; classify by `assistant.error` first.** Why: one path gives progress, session id and `rate_limit_event`; `is_error` and `subtype` differ. Rejected: `--output-format json` (J2 for text, `llm.py:115-116`). Diagram: Claude connector label "stream-json · error enum map".
- **CD4 Codex: fixed flag set, login check before the call, fail fast on two 401 events, schema adapter, system text inline, never `danger-full-access`.** Why: 1.2 rows 2, 4, 11. Rejected: `codex app-server` (marked experimental in the CLI), long-lived processes, flags for system text (unverified). Diagram: Codex connector label "login status first · read-only sandbox".
- **CD5 Usage is a delta.** Why: both CLIs report cumulative counters on resumed sessions (row 6); a naive ledger double counts. Rejected: trusting `total_cost_usd` or `usage` as per call. Diagram: ledger note "per-call delta".
- **CD6 Comparable unit: tokens always, `usd` where it exists** (Claude: list-price estimate; Codex: only with owner-supplied rates). Why: tokens exist for both; Codex has no price on the wire; ORCH expects NULL. Rejected: inventing Codex prices; converting to credits (J2 credits are Priority's budget unit). Diagram: ledger label "tokens always · usd = Claude's list-price estimate".
- **CD7 Routing policy is data** (versioned JSON, validated, the only place that names models; default = J2 behaviour; `avoid` soft constraint so an independent Audit is possible). Why: plugin precedent; the owner asked "per function and per step". Rejected: routing in code; Audit on the other provider by default (changes J2). Diagram: badge on Connector router "policy table (data)".
- **CD8 Health and quota are known without credentials and without a model call.** Sources: `auth status` / `login status`, Claude's `rate_limit_event`, Codex's own rollout (best effort), error cooldowns. Rejected: the plugin's usage-guard approach (reads Claude's keychain token, `bin/sutra-usage:73`, against ADR-035 §3). Diagram: router line "checks sign-in and quota first (no model call)".
- **CD9 Sessions: one process per turn with resume; a fixed work dir under the OS temp root; the provider session is a cache of the app transcript; a switch carries the transcript deterministically.** Rejected: a long-lived Claude process (lifecycle cost); a model-written summary on a switch (cost, failure mode). Diagram: router line "carries the transcript on a switch".
- **CD10 Allowance gate [S1-contracts-06]:** the caller that owns the envelope enforces it. The engine (`J2Run`) keeps credits, `model_call_limit` and `retry_limit` in its own accounting and sends `allowance=None`; the chat agent sends none; the router applies its ceiling of 6 invocations and the call timeout, and enforces an `Allowance` (calls, usd, deadline) inside one request only when a caller sends one, reporting `calls_made` (the capability stays for the function-node layer). Credits are never converted to usd. Why: J2 never counted the llm layer's retry and does not enforce `time_limit_minutes` or `stop_loss`, and two counters are two truths. Rejected: `max_calls` = remaining J2 calls (it would forbid the router's one retry and break J2 parity); converting credits to usd; a second independent counter in the router. Diagram: router box label "envelope kept by caller · router ceiling 6".
- **CD11 No silent offline.** The stub runs only for tests, `SUTRA_OFFLINE=1` / `--offline`, `SUTRA_CONNECTOR=stub` or the engine host's mock switch (the host builds `ScriptedPort`; `make_port(PortSpec(mock=True, …))` gives the stub-only `Router`; `RunSpec` never reaches this package) [S1-contracts-02]; with nothing usable, calls raise `NoProviderError` (J2's auto-mock when no provider, `llm.py:52`, is not kept; ENG §4.2 agrees). Diagram: chip "Offline demo".
- **CD12 JSON strategy:** native schema first, prompted fallback, pydantic repair loop (2 rounds, stateless, counted), J2's `extract_json` / `close_json` as the library's single copy (`sutra_app.library.replies`) [S2-models-12]; a schema whose native call ended in a structured error is remembered per process and later sent prompted (`native_blocked`) [S2-models-04]; business rules stay with the caller. Rejected: hidden repair inside `complete()` (it would hide calls from the engine's envelope).
- **CD13 Billing guard [S1-contracts-17]:** an API-key login is refused, with no override (`allow_api_key_billing` is removed from the policy file and from `probe_auth`); only a positive `api_key` status is refused, an unknown method is allowed. Why: D7's reason is "no API billing", and a flag that re-allows API billing would contradict a diagram line that says "never". Rejected: "ChatGPT login (an API-key login is refused unless allowed)" (56 characters, does not fit its box, and keeps an escape hatch). Diagram: the Codex connector's second line "ChatGPT login or API key in the keychain" becomes "your ChatGPT login, never an API key". Sutra never reads or stores either login.
- **CD14 Tools: one stdlib MCP server for both CLIs; all tools read-only; the DB opened `mode=ro`.** Rejected: the `mcp` SDK (a new dependency for five tools); write tools (validated structured replies instead). Diagram: dashed arrow "tools → Codex CLI" added (verified).
- **CD15 GitHub through `gh` read tools; no token in Sutra.** Rejected: porting the plugin's GitHub App device-flow platform (credential store, database, charter prohibitions); a PAT in a config.
- **CD16 Claude-held Gmail, Drive, Slack: shown, not implemented**, per ADR-035 (manual refresh, proof of presence, no account). Diagram: the dashed box keeps "Claude-held" with this badge.
- **CD17 Sign-in and install [S1-contracts-17]:** Claude is detected only; Codex sign-in is launched by the app (device flow); Sutra never installs a CLI. Diagram: the Codex CLI box text "installed and signed in through Sutra" becomes "on this Mac · signed in via Sutra" (33 characters; the earlier proposal "installed on this Mac · signed in through Sutra" has 47 and does not fit); the Claude CLI box "signed in on this Mac" stays.
- **CD18 Stub and fakes:** the stub honours J2's `mock` callable; fake `claude` / `codex` / `gh` replay captured fixtures; derived fixtures are labelled and their unverified wording listed. Diagram: new dashed box "Stub connector (tests, offline)".

## 10. Risks and unverified items
1. **Cumulative counters** could change per CLI version; `test_live` asserts delta ≥ 0 and the rule takes a smaller counter whole.
2. **UNVERIFIED, not exercised with a real model** (the two calls per CLI were spent on schema and resume): Codex strict schema against the real API; Codex image input; Codex system text via flags; MCP tool calls by a model on either CLI (permission flags are accepted, no call was made); `--max-budget-usd` behaviour; Codex non-message item fields; the Codex API-key status wording; `claude mcp list` output. `test_live` covers the first five. Also UNVERIFIED: whether either CLI accepts `anyOf` of objects in a native schema (the library's chart-ops union); the library's live check `tests/library/test_lib_live_transport.py` decides it, and a failure is absorbed by `native_blocked` and the prompted path [S2-models-04].
3. **Derived fixtures** carry unverified wording (listed in `MANIFEST.json`); matching is by substrings and falls back to `provider_error`.
4. **Codex fixed prefix** is about 12k tokens per call: short chatty calls should stay on Claude (policy).
5. **Concurrency** limits are per process (D9 runs are processes); many parallel runs can exceed plan limits and surface as `quota` / `rate_limited`; a shared limiter is later work.
6. **CLI memory files** (`CLAUDE.md`, `AGENTS.md`, user-level) are not provably disabled in `-p` mode; work dirs sit under the OS temp root; a user-level file would still apply.
7. **The allowlist** can break gateway or proxy setups; `extra_env` is the escape hatch.
8. **Version drift:** unknown flags fail fast (exit 1 or 2, mapped); `--help` feature detection warns instead of failing.
9. **CLIs keep chat transcripts** in their own folders when a chat session is used; `forget()` removes them. The wiring is complete; the first caller of `chat_send` is a later feature (v1 calls are one-shot) [S1-contracts-08].
10. **Probe leftovers** (1.2) were not removed: the task forbade changing state outside the repo and /tmp.
11. *(Closed [S1-contracts-05] [S1-contracts-08]; the number is kept so references stay valid.)* The agreements A1-A4 are settled (section 9): the Router builds every usage row and the server alone writes the ledger.
12. **Function-node coupling** is `CallTag` only: the engine host and the chat agent set `tag.atom` on every call, and a call that arrives without it is stored with a NULL `atom_id`, so a new caller must set it or its cost is not attributed to an atom [S4-fnodes-07].
