"""Tool registry.

`resource_fields` is what lets one generic matcher serve every tool: it names
which argument supplies a rule's repo pattern and which supplies the qualifier.
Adding a provider means adding ToolDefs, not matcher code.

Deliberately absent, and not merely denied by default: repository.create,
repository.delete and org.settings.write. The corresponding GitHub App
permissions are not requested, so no rule, mode or hook can reach them and the
credential itself cannot perform them. A policy toggle that could enable
repository deletion is a toggle that will eventually be enabled by accident.
"""
from dataclasses import dataclass
from typing import Dict, Iterable, Optional


@dataclass(frozen=True)
class ToolDef:
    name: str
    family: str                      # repository | contents | branches | pull_requests | issues
    write: bool = False
    destructive: bool = False
    #: Prompts in EVERY mode including bypassPermissions; denied in dontAsk.
    #: No allow rule overrides this. Claude's equivalent: connector tools an org
    #: set to `ask`, and MCP tools marked requiresUserInteraction.
    requires_user_interaction: bool = False
    repo_field: str = "repository"
    qualifier_field: Optional[str] = None
    #: When set, the tool becomes requires_user_interaction if the qualifier
    #: resolves to a protected ref. Blast radius is the target, not the verb.
    protected_ref_sensitive: bool = False


GITHUB_TOOLS = (
    # ---- read ----
    ToolDef("github.list_repositories", "repository"),
    ToolDef("github.get_repository", "repository"),
    ToolDef("github.list_branches", "branches", qualifier_field="branch"),
    ToolDef("github.get_file", "contents", qualifier_field="path"),
    ToolDef("github.get_directory", "contents", qualifier_field="path"),
    ToolDef("github.search_code", "contents", qualifier_field="path"),
    ToolDef("github.get_pull_request", "pull_requests", qualifier_field="base"),
    ToolDef("github.list_pull_requests", "pull_requests", qualifier_field="base"),
    ToolDef("github.get_issue", "issues"),
    # ---- content write ----
    ToolDef("github.create_branch", "branches", write=True, qualifier_field="branch"),
    ToolDef("github.create_commit", "contents", write=True, qualifier_field="branch",
            protected_ref_sensitive=True),
    ToolDef("github.create_pull_request", "pull_requests", write=True, qualifier_field="base"),
    ToolDef("github.update_pull_request", "pull_requests", write=True, qualifier_field="base"),
    ToolDef("github.comment_pull_request", "pull_requests", write=True, qualifier_field="base"),
    ToolDef("github.comment_issue", "issues", write=True),
    # ---- destructive: prompts in every mode ----
    ToolDef("github.merge_pull_request", "pull_requests", write=True, destructive=True,
            requires_user_interaction=True, qualifier_field="base"),
    ToolDef("github.delete_branch", "branches", write=True, destructive=True,
            requires_user_interaction=True, qualifier_field="branch"),
)


class ToolRegistry:
    def __init__(self, tools: Iterable[ToolDef] = GITHUB_TOOLS):
        self._tools: Dict[str, ToolDef] = {t.name: t for t in tools}

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def names(self):
        return tuple(self._tools)

    def __contains__(self, name) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self):
        return len(self._tools)
