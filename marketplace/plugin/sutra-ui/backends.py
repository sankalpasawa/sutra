"""Point one chat pane at a different inference backend, without telling the OS.

WHY THIS EXISTS

Supporting a second vendor has two possible shapes. Write a native adapter for
its CLI (provider_adapters.py, the long road), or keep driving Claude Code and
redirect where it sends its requests -- because Claude Code speaks the Anthropic
Messages API, and several vendors serve a compatible one.

The redirect route was assumed to require ANTHROPIC_BASE_URL and
ANTHROPIC_AUTH_TOKEN in the process environment. That is a bad way to do it, and
billing_guard exists precisely because a stray one of those silently re-bills
every turn. An environment variable is process-wide: the token would be visible
to the terminal pane, to scheduled routines, to anything the panel spawns, and
to a login shell that inherits it.

MEASURED: THE REDIRECT WORKS, AND IT LEAKS YOUR ANTHROPIC TOKEN

`claude --settings <file>` does accept an `env` block that applies to that
invocation only, and the redirect itself works: the turn reached the other
backend, the model alias was honoured, and Sutra's MCP server stayed connected.

But the CREDENTIAL it sends is not the one in the settings file. Measured
against claude 2.1.212, with nothing in the process environment, against a
local server that logged the Authorization header:

    --settings env.ANTHROPIC_AUTH_TOKEN   -> sent sk-ant-oat01... (108 chars)
    --settings apiKeyHelper               -> sent sk-ant-oat01... (108 chars)
    --bare --settings apiKeyHelper        -> sent the backend token (correct)

The first two send the operator's Anthropic SUBSCRIPTION OAuth token to
whichever third party the base URL names. While a keychain OAuth session
exists the CLI prefers it, and neither ANTHROPIC_AUTH_TOKEN nor apiKeyHelper
in a settings file overrides that.

Only `--bare` selects the supplied credential -- and `--bare`, by the CLI's own
help, skips hooks, plugin sync, auto-memory and CLAUDE.md discovery. That is
Sutra's entire governance layer. So the two options are: redirect WITH
governance and hand your Anthropic credential to a third party, or redirect
WITHOUT governance.

Neither is shippable as a general "add a provider" mechanism, so this module
REFUSES to render a redirect unless the caller states which of those two it is
accepting. The supported way to add a vendor is a native adapter
(provider_adapters.py), which never touches the Anthropic credential at all.

This module is kept because the measurement is worth keeping, and because the
refusal is what stops the next person rediscovering the leak the hard way.

A FILE, NEVER INLINE JSON

--settings takes either. The hook alone is passed inline today, correctly --
there is nothing in it to leak. A token is different: inline JSON lands in argv,
and argv is readable by any process on the machine via `ps -eo command`. Every
settings object that carries a credential is written to a 0600 file instead.

NOT THE KEYCHAIN

Tokens live in files, not in the macOS keychain, for a measured reason:
connectors/credentials/keychain.py calls SecItemCopyMatching with no timeout,
and a keychain prompt therefore wedges a FastAPI worker until someone answers
it. A chat pane must not be able to hang the panel on an OS dialog.
"""

import json
import os
import stat

PROFILES_PATH = os.path.expanduser(
    os.environ.get("SUTRA_UI_BACKENDS", "~/.sutra-ui/backends.json"))

#: Tokens live beside the connector tokens, in the same 0700 directory with the
#: same 0600 file mode -- one place to audit, one set of permissions to reason
#: about, and it is the layout the existing tooling already reads.
TOKEN_DIR = os.path.expanduser(
    os.environ.get("SUTRA_UI_BACKEND_TOKENS", "~/.sutra-connectors/oauth"))

#: Where a rendered settings file is kept. Per profile and stable, rather than a
#: fresh temp file per spawn: the CLI reads it after the process starts, so a
#: file deleted on the way out of the spawn call is a race.
SETTINGS_DIR = os.path.expanduser(
    os.environ.get("SUTRA_UI_BACKEND_SETTINGS", "~/.sutra-ui/backends"))


class BackendError(RuntimeError):
    pass


def _private_dir(path):
    os.makedirs(path, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def load_profiles():
    """Every configured backend. Non-secret: base urls, model names, costs.

    A malformed file yields no profiles rather than an exception -- the panel
    must still open, and chat still works on the default backend.
    """
    try:
        with open(PROFILES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("backends") if isinstance(data, dict) else data
    return [r for r in (rows or []) if isinstance(r, dict) and r.get("id")]


def load_profile(pid):
    if not pid:
        return None
    for r in load_profiles():
        if r["id"] == pid:
            return r
    return None


def token_path(profile):
    name = profile.get("token_file") or (profile["id"] + ".json")
    if "/" in name or ".." in name:
        raise BackendError("token_file must be a bare filename")
    return os.path.join(TOKEN_DIR, name)


def read_token(profile):
    """The bearer credential for this backend.

    Refuses a group- or world-readable file. A credential another local account
    can read is not a credential, and silently using it would teach the operator
    that Sutra checks these things when it does not.
    """
    p = token_path(profile)
    try:
        st = os.stat(p)
    except OSError:
        raise BackendError(
            "no token for backend %r. Put it in %s as {\"token\": \"...\"} "
            "with mode 600." % (profile["id"], p))
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise BackendError(
            "%s is readable by other accounts (mode %o). chmod 600 it." %
            (p, st.st_mode & 0o777))
    try:
        with open(p, encoding="utf-8") as fh:
            blob = json.load(fh)
    except (OSError, ValueError) as e:
        raise BackendError("could not read %s: %s" % (p, e))
    tok = (blob.get("token") or blob.get("access_token") or "").strip() \
        if isinstance(blob, dict) else ""
    if not tok:
        raise BackendError("%s has no \"token\" field" % p)
    return tok


def env_block(profile):
    """The `env` the CLI should run this turn under. Values, not names, so this
    is the one function whose RESULT must never be logged."""
    out = {"ANTHROPIC_BASE_URL": profile["base_url"],
           "ANTHROPIC_AUTH_TOKEN": read_token(profile)}
    # Model aliases. Claude Code asks for opus/sonnet/haiku by name; a different
    # backend has its own names, and without this the request names a model the
    # backend has never heard of and fails as an opaque API error.
    for alias, var in (("opus", "ANTHROPIC_DEFAULT_OPUS_MODEL"),
                       ("sonnet", "ANTHROPIC_DEFAULT_SONNET_MODEL"),
                       ("haiku", "ANTHROPIC_DEFAULT_HAIKU_MODEL")):
        name = (profile.get("model_map") or {}).get(alias)
        if name:
            out[var] = name
    return out


def settings_file(profile, base_settings=None, accept=None):
    """Write the settings the CLI should run under, and return its path.

    `base_settings` is whatever Sutra already needed to pass -- today the
    PreToolUse hook that makes its own MCP tools reachable. Merged into ONE
    object because --settings takes one, and passing the flag twice would mean
    the redirect and the hook could not coexist.

    0600, and written via a temp file in the same directory so a reader never
    sees a half-written settings object with a truncated token.
    """
    # `accept` must name which measured trade-off the caller is taking:
    #   "bare"     -- will pass --bare, giving up hooks/governance
    #   "oauth"    -- accepts that the Anthropic OAuth token goes to this backend
    # Anything else refuses. There is deliberately no default: both outcomes are
    # bad enough that choosing one silently would be the bug.
    if accept not in ("bare", "oauth"):
        raise BackendError(
            "refusing to render a backend redirect for %r. Measured against "
            "claude 2.1.212: with a keychain OAuth session present, --settings "
            "sends your Anthropic subscription token (sk-ant-oat..., 108 chars) "
            "to the redirected backend, and neither ANTHROPIC_AUTH_TOKEN nor "
            "apiKeyHelper overrides it. Only --bare selects the supplied "
            "credential, and --bare skips hooks, auto-memory and CLAUDE.md -- "
            "Sutra's governance. Pass accept=\"bare\" or accept=\"oauth\" to "
            "state which you are taking, or add a native adapter instead "
            "(provider_adapters.py), which never touches the Anthropic "
            "credential." % profile.get("id"))
    d = _private_dir(SETTINGS_DIR)
    merged = dict(base_settings or {})
    merged["env"] = dict(merged.get("env") or {}, **env_block(profile))
    path = os.path.join(d, "%s.settings.json" % profile["id"])
    tmp = path + ".tmp%d" % os.getpid()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(merged, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def public_dict(profile):
    """What may be shown or logged. Never the token, and never the token's
    length -- that is a fact about a secret."""
    return {"id": profile.get("id"),
            "name": profile.get("name") or profile.get("id"),
            "base_url": profile.get("base_url"),
            "models": sorted((profile.get("model_map") or {}).values()),
            "has_token": os.path.exists(token_path(profile)),
            "cost": profile.get("cost") or {}}
