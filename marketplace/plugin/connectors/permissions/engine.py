"""The evaluation chain.

Order (design/04 §4.2), and the order is the whole design:

    0. hook returned "deny" / exit 2      -> DENY   (before rules; blocking wins)
    1. deny rule matches                  -> DENY
    2. mode hard-block (plan: any write)  -> DENY
    3. requiresUserInteraction tool       -> ASK    (DENY in dontAsk; never ALLOW)
    4. ask rule matches, or hook "ask"    -> ASK
    5. hook returned "allow"              -> ALLOW  (cannot override 0-4)
    6. allow rule matches                 -> ALLOW
    7. nothing matched                    -> the mode decides

Rule SPECIFICITY NEVER REORDERS THIS. A broad deny beats a narrow allow; a
matching ask prompts even when a more specific allow also matches. That is
Claude Code's documented behaviour and it is the property that makes a deny
rule trustworthy as policy.
"""
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Sequence, Set

from .matcher import match_param, match_qualifier, match_repo, match_tool
from .modes import HARD_BLOCK_WRITES, Mode, Outcome
from .rules import Rule, RuleKind
from .settings import PermissionSettings
from .tools import GITHUB_TOOLS, ToolDef, ToolRegistry

#: Refs where a direct write is treated as destructive regardless of the verb.
DEFAULT_PROTECTED_REFS = frozenset({"main", "master", "trunk", "release", "production"})


class HookResult(str):
    """A PreToolUse hook's decision. Hooks narrow; they never widen."""
    BLOCK = "block"
    DENY = "deny"
    ASK = "ask"
    ALLOW = "allow"
    NONE = "none"


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: Dict = field(default_factory=dict)

    def resource(self, tool_def: Optional[ToolDef]):
        """(repository, qualifier) for this call, per the tool's resource_fields."""
        if tool_def is None:
            return None, None
        repo = self.arguments.get(tool_def.repo_field)
        qualifier = (
            self.arguments.get(tool_def.qualifier_field)
            if tool_def.qualifier_field else None
        )
        return (repo if isinstance(repo, str) else None,
                qualifier if isinstance(qualifier, str) else None)


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reason: str
    step: int
    matched_rule: Optional[Rule] = None
    mode: Optional[Mode] = None

    @property
    def allowed(self) -> bool:
        return self.outcome is Outcome.ALLOW

    def __str__(self) -> str:
        rule = (" via %s [%s]" % (self.matched_rule.raw, self.matched_rule.source)
                if self.matched_rule else "")
        return "%s (step %d: %s)%s" % (self.outcome.value, self.step, self.reason, rule)


#: A safety check for `auto` mode. Returns True to auto-approve.
SafetyCheck = Callable[[ToolCall, ToolDef, Dict], bool]


def conservative_safety_check(call: ToolCall, tool_def: ToolDef, context: Dict) -> bool:
    """Default `auto`-mode check.

    NOT parity with Claude Code's trained classifier. This is a rule set, and it
    is deliberately pessimistic: reads pass; a write passes only when the
    session is untainted, the tool is neither destructive nor protected-ref
    sensitive, and the call names a repository. Anything else escalates to ASK.

    Naming it a classifier in the UI would be a lie, so the UI must not.
    """
    if context.get("tainted"):
        return False
    if not tool_def.write:
        return True
    if tool_def.destructive or tool_def.protected_ref_sensitive:
        return False
    repo, _ = call.resource(tool_def)
    return bool(repo)


class PermissionEngine:
    def __init__(
        self,
        settings: PermissionSettings,
        registry: Optional[ToolRegistry] = None,
        protected_refs: Sequence[str] = (),
        safety_check: SafetyCheck = conservative_safety_check,
        granted_repos: Optional[Sequence[str]] = None,
    ):
        self.settings = settings
        self.registry = registry or ToolRegistry(GITHUB_TOOLS)
        self.protected_refs = frozenset(protected_refs) or DEFAULT_PROTECTED_REFS
        self.safety_check = safety_check
        #: The connector's working set -- the repositories a read may touch
        #: without prompting. This is the analogue of Claude Code's working
        #: directory: reads inside it are free, reads outside it prompt.
        #: None means unrestricted and must be set deliberately, never by
        #: forgetting to pass it.
        self.granted_repos = tuple(granted_repos) if granted_repos is not None else None

    @classmethod
    def for_connector(cls, settings, granted_repos, **kwargs):
        """Construct the engine for a real connector.

        The bare constructor defaults `granted_repos` to None (unrestricted),
        which is convenient for unit tests and wrong for production: it is a
        fail-OPEN default in the authorization core. Every caller that serves a
        real tool call must come through here, so an unrestricted engine can
        only ever be built by writing None on purpose.
        """
        if granted_repos is None:
            raise ValueError(
                "granted_repos is required: pass the repositories the connector's "
                "installations actually cover, or an empty tuple for none. "
                "None (unrestricted) is not reachable through for_connector()."
            )
        return cls(settings, granted_repos=tuple(granted_repos), **kwargs)

    @property
    def unrestricted(self) -> bool:
        """True when no working set is configured. Callers serving real traffic
        should refuse to run in this state."""
        return self.granted_repos is None

    # ------------------------------------------------------------------ #
    # Tool visibility
    # ------------------------------------------------------------------ #
    def visible_tools(self):
        """Tool names the model may see.

        A BARE deny rule removes the tool from the model's context entirely, so
        it cannot propose the tool, argue for it, or be injected into calling
        it. A SCOPED deny rule leaves the tool visible and blocks matching
        calls -- Claude Code draws exactly this distinction.
        """
        removed = set()
        for rule in self.settings.by_kind(RuleKind.DENY):
            if not rule.is_bare:
                continue
            for name in self.registry.names():
                if match_tool(rule.tool_pattern, name):
                    removed.add(name)
        return tuple(n for n in self.registry.names() if n not in removed)

    # ------------------------------------------------------------------ #
    # Matching
    # ------------------------------------------------------------------ #
    def _matches(self, rule: Rule, call: ToolCall, tool_def: Optional[ToolDef]) -> bool:
        if rule.ignored:
            return False
        if not match_tool(rule.tool_pattern, call.tool):
            return False
        if rule.is_param_form:
            return match_param(rule.param_value, call.arguments.get(rule.param_name))
        repo, qualifier = call.resource(tool_def)
        return (match_repo(rule.repo_pattern, repo)
                and match_qualifier(rule.qualifier_pattern, qualifier))

    def _first_match(self, kind: RuleKind, call: ToolCall, tool_def) -> Optional[Rule]:
        for rule in self.settings.by_kind(kind):
            if self._matches(rule, call, tool_def):
                return rule
        return None

    def _in_working_set(self, repo: Optional[str]) -> bool:
        """Is this repository inside the connector's granted scope?

        A call with no repository (list_repositories) is connector-wide and is
        always in scope. A repository outside the scope is not denied -- it is
        prompted, exactly as Claude Code prompts for a path outside the working
        directory rather than refusing it.
        """
        if self.granted_repos is None:
            return True
        if repo is None:
            return True
        return any(match_repo(pattern, repo) for pattern in self.granted_repos)

    def _needs_user_interaction(self, call: ToolCall, tool_def: ToolDef) -> bool:
        if tool_def.requires_user_interaction:
            return True
        if tool_def.protected_ref_sensitive:
            _, qualifier = call.resource(tool_def)
            if qualifier is not None and qualifier in self.protected_refs:
                return True
        return False

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #
    def evaluate(
        self,
        call: ToolCall,
        mode: Optional[Mode] = None,
        hook: str = HookResult.NONE,
        session_grants: Optional[Set[str]] = None,
        tainted: bool = False,
    ) -> Decision:
        mode = self.settings.effective_mode(mode)
        session_grants = session_grants or set()
        tool_def = self.registry.get(call.tool)

        # An unknown tool is denied. Fail closed: a tool we cannot classify is a
        # tool whose blast radius we cannot bound.
        if tool_def is None:
            return Decision(Outcome.DENY, "unknown_tool", step=-1, mode=mode)

        # -- 0. hook blocks ------------------------------------------------
        if hook in (HookResult.BLOCK, HookResult.DENY):
            return Decision(Outcome.DENY, "hook_blocked", step=0, mode=mode)

        # -- 1. deny rules -------------------------------------------------
        denied = self._first_match(RuleKind.DENY, call, tool_def)
        if denied is not None:
            return Decision(Outcome.DENY, "deny_rule", step=1, matched_rule=denied, mode=mode)

        # -- 2. mode hard-block --------------------------------------------
        if mode in HARD_BLOCK_WRITES and tool_def.write:
            return Decision(Outcome.DENY, "mode_blocks_writes", step=2, mode=mode)

        # -- 3. actions no mode auto-approves ------------------------------
        if self._needs_user_interaction(call, tool_def):
            if mode is Mode.DONT_ASK:
                # dontAsk never prompts, so it denies instead -- Claude Code's
                # treatment of connector tools an org set to `ask`.
                return Decision(Outcome.DENY, "requires_user_interaction_in_dont_ask",
                                step=3, mode=mode)
            return Decision(Outcome.ASK, "requires_user_interaction", step=3, mode=mode)

        # -- 4. ask rules, and hook escalation -----------------------------
        asked = self._first_match(RuleKind.ASK, call, tool_def)
        if asked is not None:
            return Decision(Outcome.ASK, "ask_rule", step=4, matched_rule=asked, mode=mode)
        if hook == HookResult.ASK:
            return Decision(Outcome.ASK, "hook_ask", step=4, mode=mode)

        # -- 5. hook allow (skips the prompt; cannot override 0-4) ---------
        if hook == HookResult.ALLOW:
            return Decision(Outcome.ALLOW, "hook_allow", step=5, mode=mode)

        # -- 6. allow rules -------------------------------------------------
        allowed = self._first_match(RuleKind.ALLOW, call, tool_def)
        if allowed is not None:
            return Decision(Outcome.ALLOW, "allow_rule", step=6, matched_rule=allowed, mode=mode)

        # -- 7. the mode decides -------------------------------------------
        return self._mode_default(call, tool_def, mode, session_grants, tainted)

    def _mode_default(self, call, tool_def, mode, session_grants, tainted) -> Decision:
        repo, _ = call.resource(tool_def)
        grant_key = "%s|%s" % (call.tool, repo or "*")

        if mode is Mode.BYPASS:
            return Decision(Outcome.ALLOW, "mode_bypass", step=7, mode=mode)

        if mode is Mode.DONT_ASK:
            return Decision(Outcome.DENY, "mode_dont_ask", step=7, mode=mode)

        if mode is Mode.PLAN:
            # Writes were already denied at step 2; reads explore the working set.
            if self._in_working_set(repo):
                return Decision(Outcome.ALLOW, "mode_plan_read", step=7, mode=mode)
            return Decision(Outcome.ASK, "read_outside_working_set", step=7, mode=mode)

        if mode is Mode.AUTO:
            context = {"tainted": tainted, "mode": mode}
            if self.safety_check(call, tool_def, context):
                return Decision(Outcome.ALLOW, "mode_auto_safety_passed", step=7, mode=mode)
            return Decision(Outcome.ASK, "mode_auto_safety_escalated", step=7, mode=mode)

        if mode is Mode.ACCEPT_EDITS:
            if self._in_working_set(repo):
                return Decision(Outcome.ALLOW, "mode_accept_edits", step=7, mode=mode)
            return Decision(Outcome.ASK, "outside_working_set", step=7, mode=mode)

        # default / manual: prompts on first use of each tool.
        if not tool_def.write:
            if self._in_working_set(repo):
                return Decision(Outcome.ALLOW, "mode_default_read", step=7, mode=mode)
            if grant_key in session_grants:
                return Decision(Outcome.ALLOW, "session_grant", step=7, mode=mode)
            return Decision(Outcome.ASK, "read_outside_working_set", step=7, mode=mode)
        if grant_key in session_grants:
            return Decision(Outcome.ALLOW, "session_grant", step=7, mode=mode)
        return Decision(Outcome.ASK, "mode_default_prompt", step=7, mode=mode)
