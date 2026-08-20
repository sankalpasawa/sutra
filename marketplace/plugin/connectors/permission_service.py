"""P3 -- the permission layer wired to a real connector.

The engine in permissions/ is pure logic over a rule set. This module is what
turns it into a decision about a specific operator, connector and repository:

  * resolves the five settings sources from actual paths on disk
  * derives the working set (granted repositories) from the connector's
    installations, so a read outside the connector's scope prompts
  * persists "don't ask again" with the durability split Claude Code uses
  * exposes the rule set for the capability API and the UI

Permission decisions happen HERE -- in ordinary code, over files, with no model
in the loop. That is the property design/04 §4.7 exists to protect.
"""
import json
import os
import platform
from typing import Dict, List, Optional

from .database.repositories import canonical
from .errors import ConnectorError
from .models import iso, utcnow
from .permissions.engine import HookResult, PermissionEngine, ToolCall
from .permissions.modes import Mode, Outcome
from .permissions.rules import RuleKind, parse_rule
from .permissions.settings import SettingsSource, load_settings
from .permissions.tools import GITHUB_TOOLS, ToolRegistry

SETTINGS_DIRNAME = ".sutra"
SETTINGS_FILE = "settings.json"
LOCAL_SETTINGS_FILE = "settings.local.json"


def managed_settings_path() -> Optional[str]:
    """Machine-wide policy. Deliberately outside any directory the operator's
    own tooling writes: managed settings that a project could overwrite are not
    managed settings."""
    if platform.system() == "Darwin":
        return "/Library/Application Support/Sutra/managed-settings.json"
    if platform.system() == "Windows":
        return os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
                            "Sutra", "managed-settings.json")
    return "/etc/sutra/managed-settings.json"


class SettingsResolver:
    """Reads the five sources. Highest precedence first: managed, session,
    local, project, user."""

    def __init__(self, project_dir: Optional[str] = None,
                 home_dir: Optional[str] = None,
                 managed_path: Optional[str] = None):
        self.project_dir = project_dir
        self.home_dir = home_dir or os.path.expanduser("~")
        self.managed_path = managed_path if managed_path is not None else managed_settings_path()

    # -- paths ------------------------------------------------------------
    def user_path(self) -> str:
        return os.path.join(self.home_dir, SETTINGS_DIRNAME, SETTINGS_FILE)

    def project_path(self) -> Optional[str]:
        if not self.project_dir:
            return None
        return os.path.join(self.project_dir, SETTINGS_DIRNAME, SETTINGS_FILE)

    def local_path(self) -> Optional[str]:
        base = self.project_dir or os.path.join(self.home_dir, SETTINGS_DIRNAME)
        if self.project_dir:
            return os.path.join(base, SETTINGS_DIRNAME, LOCAL_SETTINGS_FILE)
        return os.path.join(base, LOCAL_SETTINGS_FILE)

    # -- reading ----------------------------------------------------------
    @staticmethod
    def _read(name, path) -> Optional[SettingsSource]:
        """A missing file is not an error. A MALFORMED one is, and it fails
        closed: an unreadable settings file must never be treated as 'no
        policy', because no policy is the widest state there is."""
        if not path or not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (ValueError, OSError) as exc:
            raise ConnectorError("settings file %s is unreadable: %s" % (path, exc))
        if not isinstance(data, dict):
            raise ConnectorError("settings file %s must contain a JSON object" % path)
        return SettingsSource(name=name, data=data, path=path)

    def sources(self, session_rules: Optional[Dict] = None) -> List[SettingsSource]:
        found = []
        for name, path in (("managed", self.managed_path),
                           ("local", self.local_path()),
                           ("project", self.project_path()),
                           ("user", self.user_path())):
            source = self._read(name, path)
            if source is not None:
                found.append(source)
        if session_rules:
            found.append(SettingsSource("session", {"permissions": session_rules}))
        return found

    def load(self, session_rules: Optional[Dict] = None):
        return load_settings(self.sources(session_rules))

    # -- writing ----------------------------------------------------------
    def persist_rule(self, rule: str, kind: str = "allow") -> str:
        """"Yes, and don't ask again" -- writes to settings.local.json.

        Local, not project: a rule one operator accepted in a modal is not a
        team policy, and committing it as one is how permission creep becomes
        someone else's problem.
        """
        path = self.local_path()
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        data = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        block = data.setdefault("permissions", {})
        rules = block.setdefault(kind, [])
        if rule not in rules:
            rules.append(rule)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        return path


class ConnectorPermissions:
    """The decision surface for one connector."""

    def __init__(self, service, operator_id: str, connector_id: str,
                 resolver: Optional[SettingsResolver] = None,
                 registry: Optional[ToolRegistry] = None):
        self.service = service
        self.operator_id = operator_id
        self.connector_id = connector_id
        self.resolver = resolver or SettingsResolver()
        self.registry = registry or ToolRegistry(GITHUB_TOOLS)
        #: Session-scoped grants. Content writes persist only for the session,
        #: mirroring Claude Code's file-modification rule, which is deliberately
        #: not saved to disk.
        self.session_grants = set()
        self._session_rules = {}

    # -- working set ------------------------------------------------------
    def granted_repos(self) -> List[str]:
        """Repositories the connector's installations actually cover.

        `repository_selection == 'all'` becomes `owner/*` rather than `*`: the
        org owner granted every repo IN THAT ACCOUNT, not every repo on GitHub.
        """
        patterns = []
        for installation in self.service.cached_installations(self.connector_id):
            if installation.repository_selection == "all":
                patterns.append("%s/*" % installation.account_login)
            else:
                rows = self.service.db.execute(
                    "SELECT payload_json FROM connector_metadata "
                    "WHERE connector_id = ? AND kind = 'repository'",
                    (self.connector_id,)).fetchall()
                for row in rows:
                    payload = json.loads(row["payload_json"])
                    if payload.get("installation_id") == installation.installation_id:
                        patterns.append(payload["full_name"])
        return patterns

    # -- engine -----------------------------------------------------------
    def engine(self, session_rules=None) -> PermissionEngine:
        settings = self.resolver.load(session_rules or self._session_rules)
        return PermissionEngine.for_connector(
            settings, self.granted_repos(), registry=self.registry)

    def settings(self):
        return self.resolver.load(self._session_rules)

    def evaluate(self, tool: str, arguments: Dict, mode=None,
                 hook: str = HookResult.NONE, tainted: bool = False):
        engine = self.engine()
        decision = engine.evaluate(
            ToolCall(tool, arguments), mode=mode, hook=hook,
            session_grants=self.session_grants, tainted=tainted)
        self._audit(tool, arguments, decision)
        return decision

    def _audit(self, tool, arguments, decision):
        result = {"allow": "SUCCESS", "ask": "PENDING_APPROVAL",
                  "deny": "DENIED"}[decision.outcome.value]
        tool_def = self.registry.get(tool)
        repo = arguments.get(tool_def.repo_field) if tool_def else None
        self.service.events.append(
            self.operator_id,
            "TOOL_DENIED" if decision.outcome is Outcome.DENY else "TOOL_EVALUATED",
            result, connector_id=self.connector_id, resource=repo, operation=tool,
            reason_code=decision.reason,
            detail={"step": decision.step,
                    "rule": decision.matched_rule.raw if decision.matched_rule else None,
                    "mode": decision.mode.value if decision.mode else None})

    def visible_tools(self) -> List[str]:
        return list(self.engine().visible_tools())

    # -- grants -----------------------------------------------------------
    def grant_for_session(self, tool: str, repository: Optional[str] = None):
        self.session_grants.add("%s|%s" % (tool, repository or "*"))

    def grant_persistently(self, rule: str) -> str:
        """Only offered when the prompt could display everything the rule would
        allow, and never for a requiresUserInteraction tool."""
        parsed = parse_rule(rule, RuleKind.ALLOW, "session")
        if parsed.ignored:
            raise ConnectorError("cannot persist rule %r: %s" % (rule, parsed.warning))
        tool_def = self.registry.get(parsed.tool_pattern)
        if tool_def is not None and tool_def.requires_user_interaction:
            raise ConnectorError(
                "%s always requires interaction; one approval, one operation"
                % parsed.tool_pattern)
        return self.resolver.persist_rule(rule, "allow")

    # -- the capability API's read model ----------------------------------
    def summary(self) -> Dict:
        settings = self.settings()
        engine = self.engine()
        by_kind = {kind.value: [
            {"rule": r.raw, "source": r.source}
            for r in settings.by_kind(kind)] for kind in RuleKind}
        return {
            "connector_id": self.connector_id,
            "mode": settings.effective_mode().value,
            "default_mode": settings.default_mode.value,
            "locks": {"bypass_disabled": settings.disable_bypass,
                      "auto_disabled": settings.disable_auto},
            "managed_rules_only": settings.allow_managed_rules_only,
            "granted_repositories": self.granted_repos(),
            "visible_tools": list(engine.visible_tools()),
            "removed_tools": [t for t in self.registry.names()
                              if t not in engine.visible_tools()],
            "rules": by_kind,
            "warnings": settings.warnings,
            "sources": [{"name": s.name, "path": s.path}
                        for s in self.resolver.sources()],
            "truth_class": "authoritative",
        }
