"""Read-only accessors over Claude's own local config.

Sutra runs on top of Claude Code, so several things the panel was hardcoding
are already known to Claude: who is signed in, and where they last worked.
Reading them beats inventing them -- the panel shipped a hardcoded "TC" avatar
(a developer's own initials, wrong for literally every other operator) and a
default workspace of ~/sutra-ui-workspace, a directory nobody works in.

RULES, same as mediated_connectors.py and for the same reason:
  - READ ONLY. Sutra never writes to Claude's stores.
  - CONFIG ONLY. Never credential material. Nothing here touches the Keychain.
  - Absence is normal, not an error. A machine with no Claude config, a fresh
    install, or a signed-out user must degrade to the documented default rather
    than raise -- these feed a panel header and a settings default, and neither
    is worth failing a page load over.
"""

import json
import os
import re

CLAUDE_JSON = os.path.expanduser("~/.claude.json")

# organizationType -> product name. A type missing here is NOT guessed at:
# plan_label() returns None and the panel shows the raw values, because a
# familiar name over a tier that means something else is exactly the
# convincing-wrong answer ADR-035 forbids.
_PLAN_LABELS = {
    "claude_free": "Claude Free",
    "claude_pro": "Claude Pro",
    "claude_max": "Claude Max",
    "claude_team": "Claude Team",
    "claude_enterprise": "Claude Enterprise",
}


def _read_claude_json():
    try:
        with open(CLAUDE_JSON, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def initials_for(name, email=""):
    """Up to two letters, from the display name if there is one.

    Deliberately NOT padded to two characters: "Sankalp" yields "S", not "SA".
    A one-word name has one initial, and inventing a second letter from the
    middle of a word produces something that looks like a typo. Claude's own
    surfaces do the same.
    """
    parts = [p for p in str(name or "").replace(".", " ").split() if p]
    if parts:
        return "".join(p[0] for p in parts[:2]).upper()
    local = str(email or "").split("@")[0]
    return local[:1].upper() if local else ""


def account():
    """Who is signed in to Claude on this machine, or None.

    None means "we do not know" -- no config, signed out, or a shape we did not
    recognise. Callers must render an unknown identity, never a placeholder that
    looks like a real one.
    """
    oa = _read_claude_json().get("oauthAccount")
    if not isinstance(oa, dict):
        return None
    name = oa.get("displayName") or ""
    email = oa.get("emailAddress") or ""
    if not (name or email):
        return None
    return {
        "display_name": name or None,
        "email": email or None,
        "initials": initials_for(name, email),
        "organization": oa.get("organizationName") or None,
    }


def plan_label(org_type, tier):
    """'Claude Max (20x)' when BOTH parts are recognised, else None.

    The multiplier is read off the tier's `_<n>x` suffix (default_claude_max_20x)
    and only decorates a product name this module knows; a known product with an
    unfamiliar tier still gets its bare name, an unknown product gets nothing.
    """
    base = _PLAN_LABELS.get(str(org_type or ""))
    if not base:
        return None
    m = re.search(r"_(\d+)x$", str(tier or ""))
    return "%s (%sx)" % (base, m.group(1)) if m else base


def _short_id(value):
    s = str(value or "")
    return s[:8] if s else None


def profile():
    """The signed-in account in full, allow-listed, or None.

    account() is the rail avatar's two fields; this is the Settings > Usage
    "Account" card: who, which plan, which organisation, on what billing, since
    when. Every key is named here on purpose -- a field Claude adds to its
    config later has to be opted in before it can reach a screen. Deliberately
    NOT forwarded: userRateLimitTier, seatTier, workspaceRole (access-control
    knobs that read as account facts and confuse the story), full UUIDs (the
    first 8 characters are enough for support). None follows account()'s rule:
    no config, signed out, or an unrecognised shape means "we do not know".
    """
    oa = _read_claude_json().get("oauthAccount")
    if not isinstance(oa, dict):
        return None
    name = oa.get("displayName") or None
    email = oa.get("emailAddress") or None
    if not (name or email):
        return None
    org_type = oa.get("organizationType") or None
    tier = oa.get("organizationRateLimitTier") or None
    fetched = oa.get("profileFetchedAt")
    extra = oa.get("hasExtraUsageEnabled")
    return {
        "display_name": name,
        "full_name": oa.get("fullName") or None,
        "email": email,
        "plan": plan_label(org_type, tier),
        "organization_type": org_type,
        "rate_limit_tier": tier,
        "billing_type": oa.get("billingType") or None,
        "subscription_created_at": oa.get("subscriptionCreatedAt") or None,
        "organization": oa.get("organizationName") or None,
        "organization_role": oa.get("organizationRole") or None,
        "account_created_at": oa.get("accountCreatedAt") or None,
        "extra_usage_enabled": extra if isinstance(extra, bool) else None,
        "trial_ends_at": oa.get("claudeCodeTrialEndsAt") or None,
        "account_id": _short_id(oa.get("accountUuid")),
        "organization_id": _short_id(oa.get("organizationUuid")),
        # Milliseconds in the file; seconds here, like every other timestamp
        # the panel is handed. This is the AGE of everything above.
        "profile_fetched_at": (fetched / 1000.0) if isinstance(fetched, (int, float)) else None,
    }


def recent_workspace(is_allowed=None):
    """The directory the operator most recently worked in with Claude, or None.

    Taken from the newest session transcript's own `cwd` field rather than by
    decoding the projects directory name: the encoded form is lossy (every
    path separator becomes the same character as a literal hyphen in a folder
    name), while `cwd` is what the session actually ran in.

    `is_allowed` is injected rather than imported so this module does not depend
    on providers.py, which imports plenty. The caller passes
    providers.workdir_allowed, and a path outside the permitted root is skipped
    rather than returned -- this value becomes an agent's cwd, and widening that
    boundary from another program's config would be a real escalation.
    """
    try:
        import session_reader
        sessions = session_reader.list_sessions(limit=12)
    except Exception:
        return None
    for s in sessions or []:
        cwd = (s or {}).get("cwd") or ""
        if not cwd:
            continue
        path = os.path.expanduser(cwd)
        if not os.path.isdir(path):
            continue                      # a workspace that has since been deleted
        if is_allowed is not None and not is_allowed(path):
            continue                      # outside the permitted root
        return path
    return None
