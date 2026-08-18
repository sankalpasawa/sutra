"""Composio connectors for the Sutra panel — one hosted MCP endpoint, N toolkits.

WHAT REPLACED WHAT
------------------
This module replaces `connectors_store.py`, which modelled a connector as "one
MCP server the operator hand-configures" and shipped a 50-entry hardcoded
preset gallery plus a live search of the open MCP registry. That model made the
operator responsible for finding a server, installing it, and pasting its
secrets — per service, forever.

Composio's CURRENT open-source connector (ComposioHQ/composio, `next` branch)
inverts that. One session is created against Composio's tool router; the session
IS an MCP endpoint; every toolkit enabled on it is reachable through that single
endpoint. The SDK's own recommended path — `composio.create(user_id, mcp=True)`
-> `session.mcp.{type,url,headers}` — is exactly what this module reproduces
over plain HTTP, so the panel gains no Python dependency:

    POST https://backend.composio.dev/api/v3/tool_router/session
         x-api-key: <COMPOSIO_API_KEY>
         {"user_id": "...", "toolkits": {"enable": ["gmail", "slack"]}, ...}
    201  {"session_id": "trs_...", "mcp": {"type": "http", "url": "..."}}

    -> mcpServers["composio"] = {"type": "http", "url": <mcp.url>,
                                 "headers": {"x-api-key": <key>}}

`composio.mcp.create(...)` (the standalone MCP-server-management API) is NOT
used: upstream marked it deprecated in favour of the session endpoint and says
in so many words "do not generate new code against composio.mcp".

WHAT AUTO-UPDATES, AND BY WHICH MECHANISM
-----------------------------------------
"The connector updates when Composio updates" is three different claims with
three different mechanisms. Conflating them is the mistake this section exists
to prevent:

  TOOLS INSIDE A TOOLKIT — Composio ships a new GMAIL_* tool.
      Nothing here updates, because nothing here holds the tool list. The MCP
      endpoint is REMOTE and served by Composio; a new tool is visible to the
      next turn with no client change at all. Latency: immediate.

  THE TOOLKIT CATALOG — Composio onboards a new app, or a tool count moves.
      Upstream publishes this as a file in the repo,
      `docs/public/data/toolkits-list.json`, refreshed on a schedule by their
      sdkrelease bot ("docs: update toolkits, API spec, and meta tools data").
      We poll that file's raw URL with a conditional GET (If-None-Match), so an
      unchanged catalog costs one 304 and no bytes. Latency: <= CATALOG_TTL.

  THE SESSION — the operator enables or disables a toolkit.
      The session is bound to the toolkit set it was created with, so it is
      re-provisioned when the fingerprint of (user_id, enabled toolkits)
      changes, or when it ages past SESSION_TTL. Latency: the next turn.

The catalog poll is LAZY and TTL-gated, never a boot-time poller, for the same
reason updates.py refuses to start one: this app is also served to a plain
browser by the CLI, and a background fetch on import would make every CLI user
phone GitHub on launch. `refresh_catalog()` is called on read when stale, and
on the Electron shell's existing update tick (main.js) — the schedule lives with
the component that has a schedule.

STORE
-----
One JSON file at ~/.sutra-ui/composio.json (outside SUTRA_NATIVE_HOME by
design — panel prefs are not governance state):

    {"api_key": str, "user_id": str, "enabled": [slug, ...],
     "session": {"session_id", "url", "type", "fingerprint", "created_at"}}

The catalog cache is a SECOND file, ~/.sutra-ui/composio-catalog.json, because
it is derived data with a different lifetime: deleting it costs one refetch,
deleting the store costs the operator their API key.

Every read is FAIL-SOFT — a missing or corrupt file reads as empty, and the
catalog degrades cache -> vendored snapshot (composio-toolkits.json, shipped
beside this file) so the screen has something to show with no network at all.
Writes are atomic (tmp + os.replace) so a crash mid-write cannot truncate.
The ONLY exceptions a caller sees are ValueError from set_auth/toggle on
genuinely bad input, and ComposioError from provisioning (which the endpoint
turns into a message, never a 500).

SECRET DISCIPLINE
-----------------
The API key is written to one file and sent to one host. It is NEVER returned
by state() (only `api_key_set` and the last four characters), never logged, and
never put in a URL — Composio authenticates it as a header, and a header does
not end up in a proxy access log the way a query string does.

SUTRA_UI_COMPOSIO / SUTRA_UI_COMPOSIO_CATALOG repoint the two files (tests set
them to a tempdir), mirroring how providers.py uses SUTRA_UI_SETTINGS.
"""
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ------------------------------------------------------------- constants ----
# Composio's production API (openapi-v3.json `servers[0]`) and the one endpoint
# we call on it. Overridable so a self-hosted or staging backend can be pointed
# somewhere else without editing code.
API_BASE = os.environ.get("SUTRA_UI_COMPOSIO_API", "https://backend.composio.dev")
SESSION_PATH = "/api/v3/tool_router/session"

# The upstream catalog file, raw. `next` is ComposioHQ/composio's DEFAULT branch
# (not `main` — checked, not assumed); the bot's scheduled sync commits there.
CATALOG_URL = os.environ.get(
    "SUTRA_UI_COMPOSIO_CATALOG_URL",
    "https://raw.githubusercontent.com/ComposioHQ/composio/next/"
    "docs/public/data/toolkits-list.json")
VENDORED_CATALOG = HERE / "composio-toolkits.json"

NET_TIMEOUT = 15          # seconds — one HTTP call, not a retry budget
CATALOG_TTL = 6 * 3600    # re-check the catalog at most every 6h
SESSION_TTL = 12 * 3600   # re-provision a session at least daily-ish

# Composio toolkit slugs are lowercase alnum plus _ and - (e.g. googlecalendar,
# text_to_pdf, ai-assistant). Anchored, and bounded so a hand-edited store
# cannot push an unbounded string into a request body.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
# The key this connector takes in the merged --mcp-config. "sutra" is Sutra's
# own server (app._sutra_mcp_config) and must never be shadowed.
SERVER_NAME = "composio"
RESERVED = "sutra"
# How many toolkits one session may enable. Composio does not document a cap;
# this one is ours, because every enabled toolkit widens what a session can
# reach and an unbounded list is a governance hole, not a feature.
MAX_ENABLED = 64

# Rebind these module attributes in tests (as test_activity does with
# sr.PROJECTS) to isolate the files. Functions read them at call time.
STORE_PATH = Path(os.path.expanduser(
    os.environ.get("SUTRA_UI_COMPOSIO", "~/.sutra-ui/composio.json")))
CATALOG_PATH = Path(os.path.expanduser(
    os.environ.get("SUTRA_UI_COMPOSIO_CATALOG", "~/.sutra-ui/composio-catalog.json")))


class ComposioError(Exception):
    """A provisioning attempt that reached a conclusion we can report: a bad
    key, a rejected toolkit, an unreachable host. Carries a message meant to be
    shown to the operator verbatim — never a stack trace, never the API key."""


# ------------------------------------------------------------------ io ------
def _read_json(path, default):
    """Parse one JSON file, or `default` on any missing/corrupt/wrong-shape
    read. Never raises — every caller here is on a path where a broken file
    must degrade, not 500."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def _write_json(path, obj):
    """Atomically write one JSON file (tmp + os.replace), matching org_api's
    convention: a crash mid-write cannot leave a truncated file. The store holds
    an API key, so the temp file is forced to 0600 and that mode survives the
    replace — a world-readable ~/.sutra-ui/composio.json would leak it.

    The mode is set with fchmod AFTER open, not by the open() mode argument:
    O_CREAT's mode is ignored when the temp file ALREADY EXISTS (a crash left it,
    or another local user pre-planted composio.json.sutra-tmp at a lax mode), and
    O_TRUNC clears only the contents, not the permission bits — so os.replace
    would carry a 0666 inode onto the secret store. fchmod forces 0600 on the
    real fd regardless of how the inode was created."""
    path = str(path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    # The tmp name is UNIQUE PER WRITER (pid + thread). A fixed "<path>.sutra-tmp"
    # let two concurrent writers of the same record interleave into ONE tmp inode,
    # and os.replace then promoted the torn JSON as the durable file — caught as a
    # 1-in-6 flake by test_teamsutra's concurrency test. A crash can strand a
    # uniquely-named tmp; that is litter, never corruption, and the next same-key
    # write does not resurrect it.
    tmp = "%s.sutra-tmp.%d.%d" % (path, os.getpid(), threading.get_ident())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)  # load-bearing when tmp pre-existed at a laxer mode
    except (OSError, AttributeError):
        pass  # a platform without fchmod still gets O_CREAT's 0600 on a fresh file
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, path)


def _http_json(method, url, headers=None, body=None, timeout=NET_TIMEOUT):
    """One HTTP call returning (status, parsed_json_or_None, response_headers).

    A non-2xx does NOT raise: Composio answers 400/401/403 with a JSON error
    body that says which of the three it is, and that body is the single most
    useful thing to show the operator. Only a transport failure raises, and it
    raises urllib's own error for the caller to translate."""
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    hdrs.setdefault("User-Agent", "sutra-ui-composio")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, _loads(raw), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        return exc.code, _loads(raw), dict(getattr(exc, "headers", {}) or {})


def _loads(raw):
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------- store ------
def _blank():
    return {"api_key": "", "user_id": "", "enabled": [], "session": {}}


def load():
    """The whole store, every field present and typed. Fail-soft: a missing or
    corrupt file, or a hand-edited bad row, yields as much as is parseable."""
    raw = _read_json(STORE_PATH, {})
    out = _blank()
    out["api_key"] = str(raw.get("api_key", "") or "").strip()
    out["user_id"] = str(raw.get("user_id", "") or "").strip()

    seen = set()
    for slug in raw.get("enabled") or []:
        slug = str(slug or "").strip().lower()
        if SLUG_RE.match(slug) and slug not in seen:
            seen.add(slug)
            out["enabled"].append(slug)
        if len(out["enabled"]) >= MAX_ENABLED:
            break

    sess = raw.get("session")
    if isinstance(sess, dict) and sess.get("url") and sess.get("session_id"):
        # created_at is coerced defensively: a hand-edited store whose
        # created_at is a non-numeric string is VALID JSON, so it survives
        # _read_json's guard and would reach an unguarded float() here. A bad
        # value degrades this ONE session row to absent (like every other
        # malformed-shape case), never raises — load() promises "never raises".
        out["session"] = {
            "session_id": str(sess.get("session_id") or ""),
            "url": str(sess.get("url") or ""),
            "type": str(sess.get("type") or "http"),
            "fingerprint": str(sess.get("fingerprint") or ""),
            "created_at": _as_float(sess.get("created_at")),
        }
    return out


def _as_float(v):
    """A float, or 0.0 for anything that will not convert. Used for stored
    timestamps a hand-edit could have corrupted."""
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def save(store):
    _write_json(STORE_PATH, store)
    return store


def set_auth(api_key=None, user_id=None):
    """Set the API key and/or the user id; returns the redacted state().

    Either may be passed alone — changing the user id must not require retyping
    the key. Passing "" for the key CLEARS it (the operator disconnecting), and
    clearing anything drops the cached session, because a session provisioned
    with the old identity must never be handed to the new one.
    """
    store = load()
    changed = False

    if api_key is not None:
        api_key = str(api_key).strip()
        if api_key and len(api_key) > 512:
            raise ValueError("that does not look like a Composio API key")
        changed = changed or api_key != store["api_key"]
        store["api_key"] = api_key

    if user_id is not None:
        user_id = str(user_id).strip()
        if len(user_id) > 128:
            raise ValueError("user id must be at most 128 characters")
        # Composio treats this as an opaque identifier from YOUR database. We
        # only reject the characters that would make it ambiguous in a JSON
        # body or a log line.
        if user_id and not re.match(r"^[\w.@+-]{1,128}$", user_id):
            raise ValueError(
                "user id may contain letters, digits, and . _ @ + - only")
        changed = changed or user_id != store["user_id"]
        store["user_id"] = user_id

    if changed:
        store["session"] = {}  # identity moved — the old session is not ours
    save(store)
    return state()


def toggle(slug, on=None):
    """Enable or disable one toolkit. `on` forces a direction; None flips.

    Returns the redacted state(). Raises ValueError for an unknown-shaped slug
    or a set that would exceed MAX_ENABLED. Any change drops the cached session
    so the next turn provisions one with the new toolkit set — the session is
    bound to the toolkits it was created with, so an unrefreshed session would
    silently keep offering a toolkit the operator just turned off.
    """
    slug = str(slug or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise ValueError("not a Composio toolkit slug: %r" % slug)

    store = load()
    enabled = list(store["enabled"])
    want = (slug not in enabled) if on is None else bool(on)

    if want and slug not in enabled:
        if len(enabled) >= MAX_ENABLED:
            raise ValueError(
                "at most %d toolkits can be enabled at once — disable one first"
                % MAX_ENABLED)
        enabled.append(slug)
    elif not want and slug in enabled:
        enabled.remove(slug)
    else:
        return state()  # already in the requested position; nothing to write

    store["enabled"] = enabled
    store["session"] = {}
    save(store)
    return state()


def state():
    """What the panel is allowed to see. The API key is NEVER in here — only
    whether one is set and its last four characters, which is enough for the
    operator to recognise which key they pasted and useless to anyone else."""
    store = load()
    key = store["api_key"]
    sess = store["session"]
    cat = _catalog_meta()
    return {
        "api_key_set": bool(key),
        "api_key_hint": ("…" + key[-4:]) if len(key) >= 4 else "",
        "user_id": store["user_id"],
        "enabled": list(store["enabled"]),
        "ready": bool(key and store["user_id"] and store["enabled"]),
        "session": {
            "active": bool(sess.get("url")),
            "session_id": sess.get("session_id", ""),
            "created_at": sess.get("created_at", 0),
            "stale": bool(sess.get("url")) and
                     sess.get("fingerprint") != _fingerprint(store),
        },
        "catalog": cat,
    }


# -------------------------------------------------------------- catalog -----
def _catalog_file():
    """The cache file's contents, or the vendored snapshot's, normalised to the
    same shape. Never raises, never returns an empty catalog while the vendored
    snapshot is readable — the screen must work offline on first run."""
    cached = _read_json(CATALOG_PATH, {})
    if isinstance(cached.get("toolkits"), list) and cached["toolkits"]:
        return cached, "cache"
    vendored = _read_json(VENDORED_CATALOG, {})
    if isinstance(vendored.get("toolkits"), list):
        return vendored, "vendored"
    return {"toolkits": []}, "none"


def _normalize_upstream(rows):
    """Upstream's toolkits-list.json rows -> our trimmed row shape.

    Upstream ships {slug, name, logo, category, toolCount, triggerCount}; we
    keep everything except `logo`, which is a pure function of the slug
    (logos.composio.dev/api/<slug>) and would double the payload for nothing.
    Pure and network-free so a fabricated payload is unit-testable."""
    out, seen = [], set()
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        slug = str(row.get("slug") or "").strip().lower()
        if not SLUG_RE.match(slug) or slug in seen:
            continue
        seen.add(slug)
        out.append({
            "slug": slug,
            "name": str(row.get("name") or slug),
            "category": str(row.get("category") or "other"),
            "tools": _int(row.get("toolCount")),
            "triggers": _int(row.get("triggerCount")),
        })
    out.sort(key=lambda t: (-t["tools"], t["slug"]))
    return out


def _int(v):
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return 0


def _catalog_meta():
    """Provenance for the catalog the UI is showing: where it came from, how
    many toolkits, when we last CHECKED, and when it last actually CHANGED.
    Checked and changed are different facts and the screen states both."""
    cat, source = _catalog_file()
    # Which BYTES we hold. For a fetched copy that is the ETag, which GitHub
    # sets to the file's git blob hash; for the vendored snapshot it is the
    # commit it was cut from. Reported so "checked, unchanged" is verifiable
    # rather than something the operator has to take on trust.
    content_id = (str(cat.get("etag") or "").strip('"')
                  or str(cat.get("upstream_commit") or ""))
    return {
        "count": len(cat.get("toolkits") or []),
        "source": source,
        "checked_at": float(cat.get("checked_at") or 0),
        "updated_at": float(cat.get("updated_at") or 0),
        "content_id": content_id[:12],
        "url": CATALOG_URL,
        "ttl": CATALOG_TTL,
    }


def catalog(q="", limit=60, offset=0):
    """Search the toolkit catalog. Returns {results, total, source, ...}.

    Matches slug OR name, case-insensitively, as a substring — a catalog of
    1181 apps is browsed by typing three letters, not by exact match. Results
    keep the file's order (most tools first), so an empty query shows the
    toolkits most likely to be wanted rather than an alphabetical accident.
    """
    cat, source = _catalog_file()
    rows = cat.get("toolkits") or []
    q = str(q or "").strip().lower()
    if q:
        rows = [r for r in rows
                if q in r.get("slug", "") or q in str(r.get("name", "")).lower()]

    limit = max(1, min(_int(limit) or 60, 200))
    offset = max(0, _int(offset))
    enabled = set(load()["enabled"])
    page = [dict(r, enabled=r.get("slug") in enabled)
            for r in rows[offset:offset + limit]]
    return {
        "results": page,
        "total": len(rows),
        "offset": offset,
        "limit": limit,
        "source": source,
        "catalog": _catalog_meta(),
    }


def catalog_is_stale():
    """True when the catalog has not been checked within CATALOG_TTL. Separated
    from refresh_catalog so a caller can decide whether to pay for the network
    without the refresh deciding for it."""
    cat, _ = _catalog_file()
    return (time.time() - float(cat.get("checked_at") or 0)) > CATALOG_TTL


def refresh_catalog(force=False):
    """Conditional GET of the upstream catalog. THE auto-update mechanism.

    Returns {checked, updated, count, error, ...} and NEVER raises: a machine
    that is offline, behind a proxy, or rate-limited must keep the catalog it
    has. `force=False` is a no-op inside CATALOG_TTL, so this is safe to call on
    every screen open and on every Electron update tick.

    ETag, not a version number: upstream publishes no version for this file, and
    a 304 costs one round trip with no body — which is what makes a 6-hour poll
    of a 227KB file free in the common case where the bot has not run.
    """
    cat, source = _catalog_file()
    if not force and not catalog_is_stale():
        return {"checked": False, "updated": False, "reason": "fresh",
                "catalog": _catalog_meta()}

    headers = {}
    etag = str(cat.get("etag") or "")
    # Only send If-None-Match when the etag describes the payload we ACTUALLY
    # hold. The vendored snapshot has no etag, so first run always fetches.
    if etag and source == "cache":
        headers["If-None-Match"] = etag

    now = time.time()
    try:
        status, payload, resp_headers = _http_json("GET", CATALOG_URL, headers)
    except Exception as exc:  # transport failure of any kind
        return {"checked": True, "updated": False,
                "error": _net_message(exc), "catalog": _catalog_meta()}

    if status == 304:
        cat["checked_at"] = now
        _write_json(CATALOG_PATH, cat)
        return {"checked": True, "updated": False, "reason": "unchanged",
                "catalog": _catalog_meta()}

    if status != 200 or payload is None:
        return {"checked": True, "updated": False,
                "error": "catalog fetch returned HTTP %s" % status,
                "catalog": _catalog_meta()}

    toolkits = _normalize_upstream(payload)
    if not toolkits:
        # A 200 that parses to nothing is upstream changing shape on us. Keep
        # what we have and SAY so, rather than blanking the screen.
        return {"checked": True, "updated": False,
                "error": "upstream catalog parsed to zero toolkits — keeping "
                         "the copy we have",
                "catalog": _catalog_meta()}

    before = {(r.get("slug")) for r in (cat.get("toolkits") or [])}
    after = {r["slug"] for r in toolkits}
    changed = (before != after) or len(cat.get("toolkits") or []) != len(toolkits)

    _write_json(CATALOG_PATH, {
        "toolkits": toolkits,
        "etag": str(resp_headers.get("ETag") or resp_headers.get("etag") or ""),
        "checked_at": now,
        "updated_at": now if changed else float(cat.get("updated_at") or now),
        "source_url": CATALOG_URL,
    })
    return {
        "checked": True,
        "updated": bool(changed),
        "added": sorted(after - before)[:20],
        "removed": sorted(before - after)[:20],
        "count": len(toolkits),
        "catalog": _catalog_meta(),
    }


def _host_message(url, exc):
    """A transport failure as one line naming the host we could not reach.

    urlopen does NOT only raise URLError: a connect timeout surfaces as a bare
    TimeoutError (Python 3.10+), a reset as ConnectionResetError, and other
    failures as plain OSError — none of which carry a `.reason`. Naming the host
    only for URLError left the most common unreachable-host case ("timed out")
    with no host at all. So the host is prepended for ANY transport exception,
    and urllib's reason is appended when it has one."""
    host = urllib.parse.urlsplit(url).netloc or url
    reason = getattr(exc, "reason", None) or str(exc) or exc.__class__.__name__
    return "could not reach %s (%s)" % (host, reason)


def _net_message(exc):
    return _host_message(CATALOG_URL, exc)


# -------------------------------------------------------------- session -----
def _fingerprint(store):
    """The identity of the session we WOULD create for this store. Any change
    to the user id or the enabled set changes it, which is what makes a stale
    session detectable without asking Composio."""
    material = "%s\0%s" % (store["user_id"], ",".join(sorted(store["enabled"])))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _session_usable(store):
    sess = store["session"]
    if not sess.get("url"):
        return False
    if sess.get("fingerprint") != _fingerprint(store):
        return False
    return (time.time() - float(sess.get("created_at") or 0)) < SESSION_TTL


def provision(force=False):
    """Create a tool router session and cache it. Returns the session dict.

    This is the ONE call that reaches Composio's API. The body mirrors
    `composio.create(user_id, mcp=True)` from the SDK, with two deliberate
    narrowings:

      toolkits.enable   the operator's set, an ALLOWLIST. Composio's default is
                        "every toolkit", which would hand a session reach the
                        operator never granted.
      workbench.enable  FALSE. The workbench is a remote code-execution sandbox
                        (COMPOSIO_REMOTE_WORKBENCH / COMPOSIO_REMOTE_BASH_TOOL).
                        connectors/CHARTER.md RULE 2 forbids Sutra using
                        Composio's workbench surface, and a desktop panel has no
                        use for a remote bash tool it cannot audit.

    manage_connections is left at its default (enabled), which is what makes
    per-toolkit OAuth work without this module implementing an OAuth flow: the
    session exposes COMPOSIO_MANAGE_CONNECTIONS, and the agent hands the
    operator a branded auth link in-browser when a toolkit is not yet connected.

    Raises ComposioError with a shown-to-the-operator message on any refusal.
    """
    store = load()
    if not force and _session_usable(store):
        return store["session"]

    if not store["api_key"]:
        raise ComposioError("no Composio API key set")
    if not store["user_id"]:
        raise ComposioError("no user id set")
    if not store["enabled"]:
        raise ComposioError("no toolkits enabled")

    body = {
        "user_id": store["user_id"],
        "toolkits": {"enable": list(store["enabled"])},
        "workbench": {"enable": False},
    }
    try:
        status, payload, _ = _http_json(
            "POST", API_BASE + SESSION_PATH,
            headers={"x-api-key": store["api_key"]}, body=body)
    except Exception as exc:
        raise ComposioError(_reach_message(exc)) from exc

    if status in (401, 403):
        raise ComposioError("Composio rejected the API key (HTTP %d)" % status)
    if status >= 400:
        raise ComposioError("Composio refused the session: %s"
                            % _api_error(payload, status))
    if not isinstance(payload, dict):
        raise ComposioError("Composio returned a response we could not parse")

    mcp = payload.get("mcp") if isinstance(payload.get("mcp"), dict) else {}
    url = str(mcp.get("url") or "").strip()
    if not url:
        raise ComposioError("Composio returned a session with no MCP url")

    session = {
        "session_id": str(payload.get("session_id") or ""),
        "url": url,
        # Upstream's schema currently enums this to "http"; we read it rather
        # than hardcode it so an added "sse" arrives without a code change.
        "type": "sse" if str(mcp.get("type") or "").lower() == "sse" else "http",
        "fingerprint": _fingerprint(store),
        "created_at": time.time(),
    }
    store["session"] = session
    save(store)
    return session


def _api_error(payload, status):
    """Composio's error body as one line. Falls back to the status code."""
    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            v = payload.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:300]
            if isinstance(v, dict) and isinstance(v.get("message"), str):
                return v["message"].strip()[:300]
    return "HTTP %d" % status


def _reach_message(exc):
    return _host_message(API_BASE, exc)


def disconnect():
    """Forget the cached session (not the credentials). The next turn provisions
    a fresh one; Composio expires the abandoned one on its own schedule."""
    store = load()
    store["session"] = {}
    save(store)
    return state()


# --------------------------------------------------------------- merge ------
def mcp_servers_fragment():
    """The ENABLED connector as {name: server_spec}, ready to splat alongside
    "sutra" in app._sutra_mcp_config:

        {"composio": {"type": "http", "url": <session url>,
                      "headers": {"x-api-key": <key>}}}

    ONE server, however many toolkits — that is the whole point of the tool
    router. `{}` when nothing is configured, so the caller can splat
    unconditionally.

    FAIL-SOFT BY CONTRACT: this runs on the hot path of every turn, so a
    provisioning failure returns {} rather than raising. A turn without the
    Composio connector is degraded; a turn that does not start is broken.

    The key rides in a header exactly as the SDK does it
    (ToolRouter._create_mcp_server_config sets {"x-api-key": client.api_key}),
    and never in the url.
    """
    store = load()
    if not (store["api_key"] and store["user_id"] and store["enabled"]):
        return {}
    try:
        session = provision()
    except ComposioError:
        return {}
    except Exception:
        return {}
    if not session.get("url"):
        return {}
    return {SERVER_NAME: {
        "type": session.get("type") or "http",
        "url": session["url"],
        "headers": {"x-api-key": store["api_key"]},
    }}
