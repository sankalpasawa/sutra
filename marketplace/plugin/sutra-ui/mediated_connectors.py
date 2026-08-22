"""Connections Sutra OBSERVES but does not own -- "mediated" connectors.

WHY THIS IS A SEPARATE MODULE AND NOT A PROVIDER

`connectors/` models connections Sutra owns: it runs the OAuth, it holds the
token, it can revoke. ADR-034 makes that ownership the whole point. A Google
connection authorised inside Claude is the opposite of that in every respect,
and the data model says so out loud -- Credential rejects an empty
access_token, oauth_transactions.strategy is CHECK-constrained to the three
strategies Sutra implements, and connectors.provider_account_id is NOT NULL.
Registering Google there would mean inventing an account id, a strategy and a
token for a connection we have none of. The schema would force us to lie.

So this module sits beside providers.py -- the other "look at what a different
program is doing and report it honestly" module -- and deliberately imports
nothing from connectors.*. It cannot reach the CredentialStore, the connector
DB or the OAuth machinery, because it has no business there.

WHAT IS AND IS NOT KNOWABLE  (measured 2026-08-22, claude 2.1.212)

`claude mcp list` does two different things and prints them on one line:

  MEMBERSHIP is durable.  The connector list comes from the operator's account
  (GET /v1/mcp_servers). "This account has a Gmail connector" is a fact.

  STATUS is a five-second probe.  For every row the CLI opens an MCP
  connection and calls listTools with a 5s timeout. The result is whatever
  happened in those five seconds. Observed on an unchanged machine minutes
  apart: the same Gmail connector reported `! Connected - tools fetch failed`
  and then `+ Connected`. Rendering that as a state would make the tile
  contradict itself while nothing changed.

So membership is rendered as state, and every probe result is rendered as a
timestamped OBSERVATION attributed to the check -- "Claude's last check
reported X" -- never as a claim about the connector.

THE ACCOUNT IS NOT KNOWABLE. The /v1/mcp_servers payload carries
id/url/display_name/icon_url/tools/... and no account, email or subject. No
local store records the binding either. Neither Google MCP server exposes a
whoami tool and their scopes contain no openid/email/profile, so even a fully
credentialed caller could not ask. The tile therefore says the account is not
visible rather than showing one.

The trap that makes this worth stating twice: ~/.claude.json oauthAccount.
emailAddress is the CLAUDE account, it is frequently an @gmail.com address,
and Claude injects it into every session as plain text. An implementer has a
gmail-shaped string within reach at all times. It is not the connected Google
account and must never be rendered as one.

CHECKING IS NOT FREE AND NOT INERT. Each check spawns the CLI, which opens a
live connection to every one of the operator's connectors and rewrites
~/.claude/mcp-needs-auth-cache.json. Sutra cannot observe this without
changing another program's state. That is why the check is MANUAL, rate
limited, single-flight, and disclosed on the tile.
"""

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time

import providers

# ---------------------------------------------------------------- services --
# Keyed by URL HOST, not display name: the CLI takes display names from a
# server-supplied field and appends " (2)" when two collide, so the name is
# neither stable nor unique. The host is both.
SERVICES = (
    {"key": "gmail",  "name": "Gmail",        "host": "gmailmcp.googleapis.com"},
    {"key": "gdrive", "name": "Google Drive", "host": "drivemcp.googleapis.com"},
)

MANAGE_URL = "https://claude.ai/customize/connectors"

# 30s, not 12s. A cold first run measured 8.55s (the CLI is a 244MB Mach-O) and
# the probe contacts every connector, so a slow link with several connectors
# legitimately takes longer. Nothing blocks on this -- it is a lazy fetch off
# the render path -- so a long tail costs a late tile and nothing else.
CHECK_TIMEOUT_S = 30

# One real check per minute. The probe mutates another program's state and
# holds sockets open; a page that can trigger it in a loop is a resource bug
# and an abuse of the operator's Claude credentials.
MIN_INTERVAL_S = 60

# Never inherit the backend's environment. It carries SUTRA_DESKTOP_TOKEN --
# which authorises replacing /Applications/Sutra.app -- plus any provider
# client secrets the operator exported. Those would be inherited by `claude`
# AND by every process it starts: stdio MCP servers, hooks, tool subprocesses.
# An ALLOWLIST, so adding a new Sutra secret cannot silently widen this.
_ENV_ALLOW = ("PATH", "HOME", "USER", "LOGNAME", "SHELL",
              "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE")

# An explicit constant, not os.getcwd(): the CLI enumerates project-scoped
# servers from the working directory, so running it inside a cloned repo that
# ships a .mcp.json would execute that repo's stdio command. A screen render
# must never become repo-supplied code execution.
_SAFE_CWD = tempfile.gettempdir()

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# The transport tag is optional so a cosmetic CLI change ("(HTTP)") degrades
# one row to unknown instead of silently emptying the whole tile.
_ROW = re.compile(
    r"^(?P<name>[^:]+):\s+(?P<url>https?://\S+)(?:\s+\([A-Z]+\))?\s+-\s+(?P<status>.+)$")
# Status strings begin with a sentinel glyph the eye ignores and startswith()
# does not. Stripping it is what makes classification work at all.
_SENTINELS = "!✔✓⏸✗×✖•*-– "

_lock = threading.Lock()
_state = {"payload": None, "at": 0.0}


def _child_env():
    env = {k: os.environ[k] for k in _ENV_ALLOW if k in os.environ}
    env["NO_COLOR"] = "1"      # belt: keep ANSI out of what we parse
    env["TERM"] = "dumb"       # braces: stop the CLI reaching for a pty
    return env


def claude_bin():
    """Resolve the CLI the same way the rest of the app does.

    providers.ensure_login_path() exists because a GUI launch inherits a
    minimal PATH that does not contain /opt/homebrew/bin, so a bare
    which("claude") fails for an app opened from the Dock while succeeding in
    every terminal a developer tries it in.
    """
    try:
        providers.ensure_login_path()
    except Exception:
        pass
    return shutil.which(providers._bin_for("claude", "claude"))


def _clean(text, limit):
    """Printable ASCII only, capped. This text is CLI output and reaches the
    DOM; the renderer escapes it, and this makes sure control bytes never get
    that far either. Not a substitute for escaping -- the layer before it."""
    if not text:
        return ""
    text = _ANSI.sub("", str(text))
    # Transliterate the separators the CLI actually uses before dropping
    # non-ASCII, or "Connected · tools fetch failed" collapses to a double
    # space and reads like a typo.
    for src, dst in (("\u00b7", "-"), ("\u2013", "-"), ("\u2014", "-"),
                     ("\u2018", "'"), ("\u2019", "'"),
                     ("\u201c", '"'), ("\u201d", '"')):
        text = text.replace(src, dst)
    text = "".join(c for c in text if "\x20" <= c <= "\x7e")
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip()
    return text[:limit]


def _strip_sentinel(status):
    return status.lstrip(_SENTINELS).strip()


def classify(status):
    """A probe OUTCOME, never a connector state. Unrecognised -> 'unknown'."""
    s = _strip_sentinel(status).lower()
    if s.startswith("connected"):
        # "Connected - tools fetch failed" is the CLI reaching the server but
        # failing to list its tools. Reported, not interpreted.
        return "degraded" if ("failed" in s or "·" in status) else "connected"
    if "needs authentication" in s:
        return "needs_auth"
    if "pending approval" in s:
        return "pending_approval"
    if "not configured" in s:
        return "not_configured"
    if "failed to connect" in s or "connection error" in s:
        return "probe_failed"
    return "unknown"


def parse(text):
    """-> (saw_claudeai_row, {host: [row, ...]})

    Two jobs, deliberately decoupled. Proof-of-fetch asks only whether any line
    names a claude.ai server, with NO shape requirement: if it were derived
    from the strict row regex, a cosmetic format change would make the tile
    announce "no claude.ai connectors" -- a false statement -- for everyone who
    upgraded the CLI. Row parsing keeps the strict regex and degrades per row.
    """
    saw = False
    by_host = {}
    for raw_line in (text or "").splitlines():
        line = _ANSI.sub("", raw_line).strip()
        if not line:
            continue
        if line.startswith("claude.ai "):
            saw = True
        m = _ROW.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        if not name.startswith("claude.ai "):
            continue                      # only claude.ai-scoped rows belong here
        url = m.group("url")
        host = re.sub(r"^https?://", "", url).split("/")[0].split(":")[0].lower()
        # Strip the sentinel for the STORED text too, not just for matching.
        # "✔" is non-ASCII and _clean drops it while "!" survives, so without
        # this the diagnostic line reads "Connected" for one row and
        # "! Needs authentication" for the next -- same field, two shapes.
        status = _clean(_strip_sentinel(_ANSI.sub("", m.group("status"))), 120)
        by_host.setdefault(host, []).append({
            "label": _clean(name, 80),
            "observation": classify(status),
            "raw_status": status,
        })
    return saw, by_host


# Worst-first. A host with two connectors in disagreeing states must roll up to
# the WORSE one: hiding a dead connector behind a healthy one inverts the only
# reason this tile exists.
_SEVERITY = ("needs_auth", "probe_failed", "not_configured", "pending_approval",
             "unknown", "degraded", "connected")


def _rollup(rows):
    for kind in _SEVERITY:
        if any(r["observation"] == kind for r in rows):
            return kind
    return "unknown"


def _build(availability, detail="", saw=False, by_host=None, checked_at=None):
    by_host = by_host or {}
    services = []
    for svc in SERVICES:
        rows = by_host.get(svc["host"], [])
        if rows:
            membership = "added"
        elif availability == "ok" and saw:
            # Only ever assertable when the server list demonstrably arrived.
            membership = "not_added"
        else:
            membership = "unknown"
        services.append({
            "key": svc["key"],
            "name": svc["name"],
            "membership": membership,
            "observation": _rollup(rows) if rows else None,
            "connectors": rows,
        })
    return {
        "provider": "google",
        "name": "Google",
        "via": "claude",
        "manage_url": MANAGE_URL,
        # Machine-readable so the "we do not know the account" promise is
        # pinnable by a test rather than living only in a UI string.
        "account_known": False,
        "availability": availability,
        "availability_detail": _clean(detail, 200),
        "checked_at": checked_at,
        "services": services,
    }


def _probe():
    """One real invocation. Returns a fully-built payload."""
    binary = claude_bin()
    if not binary:
        return _build("cli_missing")
    try:
        proc = subprocess.run(
            [binary, "mcp", "list"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT_S,
            cwd=_SAFE_CWD,
            env=_child_env(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _build("timed_out", "no answer within %ds" % CHECK_TIMEOUT_S,
                      checked_at=time.time())
    except Exception as exc:
        return _build("cli_error", "%s: %s" % (type(exc).__name__, exc),
                      checked_at=time.time())

    now = time.time()
    if proc.returncode != 0:
        return _build("cli_error", proc.stderr or proc.stdout, checked_at=now)

    saw, by_host = parse(proc.stdout)
    if not saw:
        # Identical output whether the operator is offline, signed out, or
        # genuinely has no connectors. Exit status is 0 in every case, so this
        # cannot be resolved -- and must not be guessed.
        return _build("unreadable", proc.stdout, checked_at=now)
    return _build("ok", saw=True, by_host=by_host, checked_at=now)


def snapshot(refresh=False):
    """Cached view. `refresh` requests a real check; the cooldown still applies.

    Single-flight: the lock means a burst of requests produces exactly one
    subprocess, and everyone else reads the cache. Without it a page hitting
    this endpoint in a loop would spawn unbounded `claude` processes, each
    holding sockets open for up to CHECK_TIMEOUT_S.
    """
    now = time.time()
    cached, at = _state["payload"], _state["at"]
    if not refresh:
        if cached is None:
            return dict(_build("not_checked"), stale=False)
        return dict(cached, stale=(now - at) > MIN_INTERVAL_S)

    if cached is not None and (now - at) < MIN_INTERVAL_S:
        return dict(cached, stale=False, throttled=True)

    if not _lock.acquire(blocking=False):
        # Someone else is mid-probe. Answer from cache rather than queueing --
        # a queued caller would just spawn a second CLI a moment later.
        if cached is not None:
            return dict(cached, stale=True, throttled=True)
        return dict(_build("not_checked"), stale=False, throttled=True)
    try:
        payload = _probe()
        _state["payload"], _state["at"] = payload, time.time()
        return dict(payload, stale=False)
    finally:
        _lock.release()


def _reset_for_tests():
    _state["payload"], _state["at"] = None, 0.0
