"""Installation, repository and organization discovery.

The endpoints here are the GitHub APP ones, and that distinction matters: the
brief's `/user/repos` + `/user/orgs` pair is correct for an OAuth App and wrong
for a GitHub App. What a user can reach through our App is the INTERSECTION of

    repos on GitHub
      -> repos this USER can see            (their permission)
        -> repos in the Sutra INSTALLATION  (org owner's selection)
          -> repos our PERMISSIONS cover    (what the App was granted)

and only `/user/installations` + `/user/installations/{id}/repositories` reflect
that intersection. `/user/orgs` is still fetched, but for a different question:
the DIFFERENCE between "orgs you belong to" and "orgs where Sutra is installed"
is the most useful thing the connector UI can show.
"""
from typing import Dict, List, Optional, Tuple

from ..errors import SSORequired
from ..models import Installation, Organization, Repository

#: GitHub App permission -> the capabilities it underpins. Note one permission
#: backs several capabilities with very different blast radii: `contents:write`
#: is create_branch AND create_commit AND delete_branch. That is exactly why the
#: capability layer exists and why a scope is not a capability.
PERMISSION_CAPABILITIES = {
    ("metadata", "read"): ["github.repositories.read"],
    ("contents", "read"): ["github.repository.contents.read",
                           "github.repository.branches.read",
                           "github.search.code"],
    ("contents", "write"): ["github.repository.branches.write",
                            "github.repository.commits.write"],
    ("pull_requests", "read"): ["github.pull_requests.read"],
    ("pull_requests", "write"): ["github.pull_requests.write"],
    ("issues", "read"): ["github.issues.read"],
    ("issues", "write"): ["github.issues.write"],
}


def capabilities_for(permissions: Dict[str, str]) -> List[str]:
    """What the PROVIDER grant permits. The connector grant and agent policy
    narrow this further; neither widens it."""
    out = []
    for resource, level in (permissions or {}).items():
        out.extend(PERMISSION_CAPABILITIES.get((resource, "read"), [])
                   if level in ("read", "write") else [])
        if level == "write":
            out.extend(PERMISSION_CAPABILITIES.get((resource, "write"), []))
    return sorted(set(out))


class Discovery:
    def __init__(self, client):
        self.client = client

    # ---------------------------------------------------------------- #
    def list_installations(self, token: str) -> List[Installation]:
        installations: List[Installation] = []
        url = "/user/installations"
        while url:
            response = self.client._api_get(url, token)
            payload = response.json()
            for raw in payload.get("installations", []):
                installations.append(self._to_installation(raw))
            from .pagination import next_url
            url = next_url(response)
        return installations

    @staticmethod
    def _to_installation(raw: Dict) -> Installation:
        account = raw.get("account") or {}
        return Installation(
            installation_id=int(raw["id"]),
            account_login=account.get("login", ""),
            account_id=int(account.get("id", 0)),
            account_type=account.get("type", "User"),
            repository_selection=raw.get("repository_selection", "selected"),
            permissions=raw.get("permissions") or {},
            suspended=bool(raw.get("suspended_at")),
        )

    # ---------------------------------------------------------------- #
    def list_repositories(self, token, installation: Installation,
                          url: Optional[str] = None, page_limit: int = 1):
        """One page (or `page_limit` pages) of an installation's repositories.

        Returns (repositories, next_url). The caller signs next_url into a
        cursor; it is never handed to a client raw.
        """
        url = url or ("/user/installations/%d/repositories?per_page=100"
                      % installation.installation_id)
        repositories: List[Repository] = []
        pages = 0
        try:
            while url and pages < page_limit:
                response = self.client._api_get(url, token)
                payload = response.json()
                for raw in payload.get("repositories", []):
                    repositories.append(self._to_repository(raw, installation))
                from .pagination import next_url as _next
                url = _next(response)
                pages += 1
        except SSORequired:
            # The connector is fine; one organization needs a browser
            # round-trip. Returning the repos as "missing" would send the user
            # hunting for a problem that is not theirs.
            return [], None, "sso_required"
        return repositories, url, "ok"

    @staticmethod
    def _to_repository(raw: Dict, installation: Installation) -> Repository:
        owner = (raw.get("owner") or {}).get("login", "")
        permissions = raw.get("permissions") or {}
        user_permission = "read"
        for level in ("admin", "maintain", "push", "triage", "pull"):
            if permissions.get(level):
                user_permission = {"push": "write", "pull": "read"}.get(level, level)
                break
        return Repository(
            repo_id=str(raw.get("id")),
            full_name=raw.get("full_name") or "%s/%s" % (owner, raw.get("name")),
            owner=owner,
            name=raw.get("name", ""),
            visibility=raw.get("visibility") or ("private" if raw.get("private") else "public"),
            default_branch=raw.get("default_branch") or "main",
            archived=bool(raw.get("archived")),
            user_permission=user_permission,
            installation_id=installation.installation_id,
            app_permissions=dict(installation.permissions),
            capabilities=capabilities_for(installation.permissions),
        )

    # ---------------------------------------------------------------- #
    def list_organizations(self, token: str,
                           installations: List[Installation]) -> List[Organization]:
        """Memberships joined against installations.

        An org you belong to where Sutra is NOT installed is returned with
        access='not_installed' and an install action -- not omitted. A silently
        missing org is a support ticket; a labelled one is a fixable state.
        """
        by_account = {i.account_id: i for i in installations
                      if i.account_type == "Organization"}
        organizations: List[Organization] = []
        seen = set()

        url = "/user/orgs?per_page=100"
        while url:
            response = self.client._api_get(url, token)
            for raw in response.json() or []:
                account_id = int(raw.get("id", 0))
                seen.add(account_id)
                installation = by_account.get(account_id)
                organizations.append(Organization(
                    org_id=str(account_id),
                    login=raw.get("login", ""),
                    avatar_url=raw.get("avatar_url"),
                    installation=installation,
                    access="ok" if installation and not installation.suspended
                           else ("suspended" if installation else "not_installed"),
                ))
            from .pagination import next_url
            url = next_url(response)

        # An installation on an org the membership endpoint did not return --
        # possible when the user's membership is concealed. Do not drop it.
        for account_id, installation in by_account.items():
            if account_id in seen:
                continue
            organizations.append(Organization(
                org_id=str(account_id), login=installation.account_login,
                avatar_url=None, installation=installation,
                access="suspended" if installation.suspended else "ok"))
        return organizations
