"""Where a turn's inference actually goes, and whether the operator agreed to it.

THE HOLE THIS CLOSES

`ANTHROPIC_API_KEY` is guarded in seven places -- install.sh, sutra-ui.sh, app.py
twice, electron/main.js twice, routines.py -- because routing through the API
bills per token instead of the operator's Max plan. Every one of those guards
checks exactly one variable.

`ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` were checked NOWHERE. Measured by
grep across the whole tree: seven enforcement points for one variable, zero for
the two that redirect the entire backend. A single line in a shell profile

    export ANTHROPIC_BASE_URL=https://someone-elses-api.example/v1

silently sends every chat turn, every terminal session and every scheduled
routine -- prompts, file contents, whatever the agent reads -- to a third party,
while the UI continues to state that it bills the Max plan. That is a worse
failure than the one the original guard was built for: the API at least belongs
to the vendor the operator chose.

WHY AN EXPLICIT LIST AND NOT A PREFIX MATCH

The obvious fix is to refuse on anything matching `^ANTHROPIC_`. It is wrong.
`ANTHROPIC_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`
and friends select a model; they redirect nothing. A refuse-to-start guard on
that prefix bricks the app for anyone who has legitimately pinned a model. Only
variables that change WHERE the request goes, or WHO it authenticates as, belong
here -- and each is listed by name so adding one is a deliberate act.

WHY OPT-IN RATHER THAN A HARD BLOCK

A redirect is not automatically wrong: pointing the CLI at a different
Anthropic-compatible backend is exactly how a second provider would be
supported. What is wrong is doing it SILENTLY. So the default is refusal, the
override is explicit and out-of-band, and when an override is active the panel
says so rather than continuing to claim Max-plan billing. Same shape as the
existing SUTRA_UI_ALLOW_UNSAFE_PERM_MODES gate.
"""

import os

#: Every variable that can move inference off the plan. Used for SCRUBBING child
#: environments, where removing all of them is always safe: dropping a base URL
#: that already holds the official endpoint just restores the default.
REDIRECT_VARS = (
    "ANTHROPIC_BASE_URL",       # the whole backend
    "ANTHROPIC_AUTH_TOKEN",     # bearer credential for a redirected backend
    "ANTHROPIC_API_KEY",        # per-token API billing (the original guard)
    "ANTHROPIC_BEDROCK_BASE_URL",
    "ANTHROPIC_VERTEX_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
)

#: Variables whose VALUE decides whether anything is redirected. Refusing on mere
#: presence here is wrong and was the first version of this guard: Claude Code
#: itself exports ANTHROPIC_BASE_URL=https://api.anthropic.com, so a panel
#: launched from a terminal that inherited it would refuse to start over a
#: setting that changes nothing. Measured on this machine, 2026-08.
_URL_VARS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_BEDROCK_BASE_URL",
             "ANTHROPIC_VERTEX_BASE_URL")

#: Flags: only a truthy value routes anywhere. "0" and "false" are people
#: explicitly turning the thing OFF and must not be read as turning it on.
_FLAG_VARS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")

#: Credentials: presence alone moves billing to per-token, whatever the endpoint.
_CRED_VARS = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")

OFFICIAL_HOST_SUFFIX = ".anthropic.com"
OFFICIAL_HOST = "anthropic.com"

#: Out-of-band acknowledgement. Deliberately an environment variable rather than
#: a settings toggle: turning it on should require the same kind of act as
#: setting the redirect itself, not a click by someone who has not read this.
ALLOW_ENV = "SUTRA_UI_ALLOW_BACKEND_REDIRECT"

_FALSEY = ("", "0", "false", "no", "off")


def _host(url):
    u = url.strip()
    u = u.split("://", 1)[-1]
    return u.split("/", 1)[0].split("@")[-1].split(":")[0].lower()


def _is_official(url):
    h = _host(url)
    return h == OFFICIAL_HOST or h.endswith(OFFICIAL_HOST_SUFFIX)


def active_redirects(env=None):
    """Names of variables that ACTUALLY redirect, given their values. Never the
    values themselves -- this result reaches logs and API responses, and one of
    these variables is a bearer credential."""
    env = os.environ if env is None else env
    out = []
    for v in _URL_VARS:
        val = (env.get(v) or "").strip()
        if val and not _is_official(val):
            out.append(v)
    for v in _CRED_VARS:
        if (env.get(v) or "").strip():
            out.append(v)
    for v in _FLAG_VARS:
        if (env.get(v) or "").strip().lower() not in _FALSEY:
            out.append(v)
    return tuple(out)


def redirect_allowed(env=None):
    env = os.environ if env is None else env
    return (env.get(ALLOW_ENV) or "").strip() in ("1", "true", "yes")


def refusal(env=None):
    """The message to refuse a turn with, or None when it may proceed.

    Returns a string rather than raising so each caller can deliver it in its own
    channel -- a websocket frame, an ANSI line in the terminal, a startup die().
    """
    names = active_redirects(env)
    if not names or redirect_allowed(env):
        return None
    return (
        "Refused: %s set in this environment. That sends every turn -- prompts and "
        "whatever the agent reads -- to a backend other than your Max plan, which "
        "this panel otherwise tells you it is using. "
        "Fix: unset %s. To do it deliberately anyway, set %s=1 and the panel will "
        "say on screen which backend is in use."
        % (", ".join(names), " and ".join(names), ALLOW_ENV)
    )


def scrub(env, allow=None):
    """Remove every redirect variable from a child environment, in place-ish.

    HONOURS THE OPT-IN. An earlier version stripped unconditionally, which made
    ALLOW_ENV a lie: refusal() would let the turn through on the operator's
    explicit opt-in, and then this quietly removed the very variables that
    opt-in was about, so the turn ran against the default backend anyway. One
    rule in both places or the setting means nothing.

    `allow` is read from the same env by default; pass it explicitly only for a
    path that must use subscription auth no matter what.
    """
    if redirect_allowed(env) if allow is None else allow:
        return env
    for v in REDIRECT_VARS:
        env.pop(v, None)
    return env


def status(env=None):
    """What the UI should show. `redirected` true means the operator has opted in
    and the panel must stop claiming Max-plan billing."""
    names = active_redirects(env)
    return {
        "redirected": bool(names) and redirect_allowed(env),
        "vars": list(names),
        "allow_env": ALLOW_ENV,
        "blocked": bool(names) and not redirect_allowed(env),
    }
