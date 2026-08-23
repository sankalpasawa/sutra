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

CLAUDE_JSON = os.path.expanduser("~/.claude.json")


def _read_claude_json():
    try:
        with open(CLAUDE_JSON, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def initials_for(name, email=""):
    """Up to two letters, from the display name if there is one.

    Deliberately NOT padded to two characters: "Tishant" yields "T", not "TI".
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
