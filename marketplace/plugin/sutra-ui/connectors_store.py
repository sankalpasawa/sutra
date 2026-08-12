"""User-defined MCP connectors for the Sutra panel — the store + preset catalog.

WHAT THIS IS
------------
Sutra spawns `claude -p` once per turn and injects its OWN MCP server via
`--mcp-config <json> --strict-mcp-config` (see app._sutra_mcp_config). Because
`--strict-mcp-config` means "use ONLY this config", the operator's globally
configured MCP servers are invisible to a Sutra session. This module lets the
operator define connectors HERE so app.py can merge the enabled ones into that
same `--mcp-config`, alongside `sutra`, without ever touching the machine's
global ~/.claude.json.

STORE
-----
One JSON file, {"connectors": [ ... ]}, at ~/.sutra-ui/connectors.json (outside
SUTRA_NATIVE_HOME by design — panel prefs are not governance state). Each row:

    { "id": str, "name": str, "transport": "stdio"|"http"|"sse",
      "command": str, "args": [str], "env": {k: v}, "url": str,
      "headers": {k: v}, "enabled": bool }

`headers` mirrors Claude's remote-connector auth (`--header` / config `headers`):
a str->str map merged into the http/sse server spec so the operator can pass an
`Authorization: Bearer ...` (or any) header. It is meaningful only for http/sse;
validate() drops it for stdio, and the merge omits an empty map.

Every operation is FAIL-SOFT: a missing/corrupt file reads as an empty list, and
writes are atomic (tmp + os.replace) so a crash mid-write cannot leave a
truncated store. Nothing here raises for a missing store — the ONLY exception a
caller sees is ValueError from validate/add_or_update on genuinely bad input.

SUTRA_UI_CONNECTORS repoints the file (tests set it to a tempdir), mirroring how
providers.py uses SUTRA_UI_SETTINGS.
"""
import json
import os
import re
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

# name: a DNS-ish token that becomes the mcpServers key. Lowercase start, then
# letters/digits/underscore/hyphen, 1..39 chars total.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,38}$")
TRANSPORTS = ("stdio", "http", "sse")
# "sutra" is Sutra's own server (app._sutra_mcp_config). A connector may never
# take that name, or it would shadow the panel's own tools in the merged config.
RESERVED = "sutra"

# Rebind this module attribute in tests (as test_activity does with sr.PROJECTS)
# to isolate the store. Functions read it at call time, so a rebind is honoured.
CONNECTORS_PATH = Path(os.path.expanduser(
    os.environ.get("SUTRA_UI_CONNECTORS", "~/.sutra-ui/connectors.json")))


# --------------------------------------------------------------- catalog ----
# One-click presets. Blank secrets: env_keys names the env vars the operator
# must fill before enabling. Real MCP servers, npx-launched (stdio) except the
# one remote example (linear, sse). The frontend turns a picked entry into a
# connector POST — env built from env_keys, enabled decided there.
CATALOG = [
    {
        "name": "github",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env_keys": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
        "url": "",
        "description": "GitHub repos, issues and pull requests. "
                       "Needs a personal access token.",
    },
    {
        "name": "filesystem",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem",
                 os.path.expanduser("~")],
        "env_keys": [],
        "url": "",
        "description": "Read/write files under a directory you allow "
                       "(defaults to your home — edit the path arg to narrow it).",
    },
    {
        "name": "slack",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env_keys": ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
        "url": "",
        "description": "Post and read Slack messages. "
                       "Needs a bot token and a team id.",
    },
    {
        "name": "puppeteer",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer"],
        "env_keys": [],
        "url": "",
        "description": "Headless-browser automation and page scraping. No secrets.",
    },
    {
        "name": "brave-search",
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env_keys": ["BRAVE_API_KEY"],
        "url": "",
        "description": "Web search via the Brave Search API. Needs an API key.",
    },
    {
        "name": "linear",
        "transport": "sse",
        "command": "",
        "args": [],
        "env_keys": [],
        "url": "https://mcp.linear.app/sse",
        "description": "Linear issues over a remote SSE endpoint (OAuth in-browser).",
    },
]


def _new_id():
    """A stable, collision-free connector id. Prefixed so it never looks like a
    name and is obvious in a hand-edited file."""
    return "cx_" + uuid.uuid4().hex[:12]


def validate(raw):
    """Normalise one connector dict, or raise ValueError with a clear message.

    Returns a NEW dict with every field present and typed. The id is preserved
    if given but NOT generated here — add_or_update owns id lifecycle so that
    validate stays a pure check usable from load() as well.

    Rules (all rejected with a specific message):
      - name matches NAME_RE and is not the reserved "sutra"
      - transport is one of stdio|http|sse
      - stdio requires a command; http/sse requires a url
    """
    if not isinstance(raw, dict):
        raise ValueError("connector must be an object")

    name = str(raw.get("name", "")).strip()
    if not NAME_RE.match(name):
        raise ValueError(
            "name must match ^[a-z0-9][a-z0-9_-]{0,38}$ — a lowercase letter or "
            "digit, then letters/digits/underscore/hyphen, at most 39 characters")
    if name == RESERVED:
        raise ValueError('name "sutra" is reserved for Sutra\'s own MCP server')

    transport = str(raw.get("transport", "")).strip()
    if transport not in TRANSPORTS:
        raise ValueError("transport must be one of: %s" % ", ".join(TRANSPORTS))

    command = str(raw.get("command", "") or "").strip()
    url = str(raw.get("url", "") or "").strip()
    if transport == "stdio" and not command:
        raise ValueError("stdio transport requires a command")
    if transport in ("http", "sse") and not url:
        raise ValueError("%s transport requires a url" % transport)

    # args: strings only. A non-string is dropped, never stringified — passing
    # the text "None" to a subprocess is worse than passing nothing.
    args = []
    if isinstance(raw.get("args"), list):
        args = [str(a) for a in raw["args"] if isinstance(a, str)]

    # env: str->str. A blank value is KEPT — "added from the catalog, secret not
    # yet filled" is a real, distinct state the UI needs to show.
    env = {}
    if isinstance(raw.get("env"), dict):
        for k, v in raw["env"].items():
            if isinstance(k, str) and k.strip():
                env[k] = "" if v is None else str(v)

    # headers: str->str, same sanitisation as env (blank values kept — an
    # "Authorization" whose token is not yet pasted is a real UI state). Only
    # meaningful for a remote transport; for stdio it is dropped entirely so the
    # merged --mcp-config never carries a headers key on a {command,args,env} spec.
    headers = {}
    if transport in ("http", "sse") and isinstance(raw.get("headers"), dict):
        for k, v in raw["headers"].items():
            if isinstance(k, str) and k.strip():
                headers[k] = "" if v is None else str(v)

    return {
        "id": str(raw.get("id", "") or "").strip(),
        "name": name,
        "transport": transport,
        "command": command,
        "args": args,
        "env": env,
        "url": url,
        "headers": headers,
        "enabled": bool(raw.get("enabled", True)),
    }


def load():
    """Every stored connector as a list. Fail-soft: a missing or corrupt file,
    or a hand-edited bad row, yields as much as is parseable — never an
    exception. Callers (the merge, the endpoints) must never break because the
    store is absent or garbage."""
    try:
        with open(CONNECTORS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    rows = data.get("connectors") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        try:
            conn = validate(row)
        except ValueError:
            continue  # drop one bad row rather than lose the whole store
        if not conn["id"]:
            conn["id"] = _new_id()
        out.append(conn)
    return out


def save(connectors):
    """Atomically write the whole list. tmp + os.replace, matching org_api's
    file-write convention: a crash mid-write cannot leave a truncated store.
    Callers pass already-validated dicts (every mutator routes through
    validate())."""
    path = str(CONNECTORS_PATH)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".sutra-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"connectors": list(connectors)}, fh, indent=2)
    os.replace(tmp, path)


def add_or_update(raw):
    """Validate and upsert one connector; returns the stored dict.

    Assigns an id when the input has none. Matches an existing row by id
    (replace in place) else appends. Raises ValueError on a validation miss.

    Name uniqueness is enforced (excluding self): the merged --mcp-config keys
    servers by NAME, so two enabled connectors sharing a name would silently
    drop one — better a clear 400 than a vanished connector."""
    conn = validate(raw)
    conns = load()

    for other in conns:
        if other["name"] == conn["name"] and other["id"] != conn["id"]:
            raise ValueError('a connector named "%s" already exists' % conn["name"])

    if not conn["id"]:
        conn["id"] = _new_id()

    for i, other in enumerate(conns):
        if other["id"] == conn["id"]:
            conns[i] = conn
            break
    else:
        conns.append(conn)

    save(conns)
    return conn


def toggle(cid):
    """Flip `enabled` for the connector with this id. Returns the updated dict,
    or None when no connector matches (the endpoint maps None -> 404)."""
    conns = load()
    for i, conn in enumerate(conns):
        if conn["id"] == cid:
            conn["enabled"] = not conn.get("enabled", False)
            conns[i] = conn
            save(conns)
            return conn
    return None


def remove(cid):
    """Delete the connector with this id. True if one was removed, else False."""
    conns = load()
    kept = [c for c in conns if c["id"] != cid]
    if len(kept) == len(conns):
        return False
    save(kept)
    return True


def mcp_servers_fragment():
    """The ENABLED connectors as {name: server_spec}, in the shape Claude's
    --mcp-config expects, ready to splat alongside "sutra":

        stdio    -> {"command", "args", "env"}
        http/sse -> {"type": "http"|"sse", "url"[, "headers"]}

    A remote connector with a non-empty `headers` map emits it alongside url —
    this is exactly what Claude's --mcp-config accepts for authenticated remote
    servers. An empty map is omitted so a headerless connector stays byte-for-byte
    what it was before this feature.

    Only enabled rows; the reserved "sutra" name is skipped defensively (validate
    already rejects it on the way in). Fail-soft via load() — a broken store is
    an empty fragment, so app._sutra_mcp_config can splat it unconditionally."""
    out = {}
    for conn in load():
        if not conn.get("enabled"):
            continue
        name = conn.get("name")
        if not name or name == RESERVED:
            continue
        transport = conn.get("transport")
        if transport == "stdio":
            if not conn.get("command"):
                continue
            out[name] = {
                "command": conn["command"],
                "args": list(conn.get("args") or []),
                "env": dict(conn.get("env") or {}),
            }
        elif transport in ("http", "sse"):
            if not conn.get("url"):
                continue
            spec = {"type": transport, "url": conn["url"]}
            headers = conn.get("headers") or {}
            if headers:
                spec["headers"] = dict(headers)
            out[name] = spec
    return out


# ------------------------------------------------------- live MCP registry ---
# The official open registry (https://registry.modelcontextprotocol.io) lists
# thousands of servers in a shape that is NOT our catalog shape. These helpers
# fetch a page and normalise each server into the SAME dict /api/connectors/
# catalog returns, so the Add form can prefill from either source identically:
#
#     {name, title, description, transport, command, args:[...],
#      env_keys:[...], url}
#
# The pure normaliser (normalize_registry_servers) is deliberately network-free
# so it is unit-testable against a fabricated payload; fetch_registry does the
# one urllib call and the app endpoint wraps both with a fail-soft to the
# built-in CATALOG.

REGISTRY_URL = "https://registry.modelcontextprotocol.io/v0.1/servers"
REGISTRY_TIMEOUT = 6  # seconds — a slow registry must not stall the Add panel.
# registryType -> the local launcher a stdio package server runs under.
_PKG_COMMAND = {"npm": "npx", "pypi": "uvx", "oci": "docker"}


def catalog_normalized():
    """The built-in CATALOG in the registry-result shape (adds `title`, keeps
    `env_keys`). This is the fail-soft payload the registry endpoint returns when
    the network is down or a query has zero hits, so the Add form always has
    something to show."""
    out = []
    for e in CATALOG:
        out.append({
            "name": e["name"],
            "title": e.get("title") or e["name"],
            "description": e.get("description", ""),
            "transport": e["transport"],
            "command": e.get("command", ""),
            "args": list(e.get("args") or []),
            "env_keys": list(e.get("env_keys") or []),
            "url": e.get("url", ""),
        })
    return out


def _slug_from_registry_name(full_name):
    """A valid connector `name` from a registry server.name like
    "io.github.owner/my-server": take the last '/'-segment, lowercase it, map any
    char outside [a-z0-9_-] to '-', strip leading non-alphanumerics, and trim to
    39 chars. Returns None when nothing valid survives, or when it would collide
    with the reserved "sutra"."""
    seg = str(full_name or "").rsplit("/", 1)[-1].lower()
    seg = re.sub(r"[^a-z0-9_-]", "-", seg)
    seg = re.sub(r"^[^a-z0-9]+", "", seg)  # first char must be [a-z0-9]
    seg = seg[:39]
    if not NAME_RE.match(seg) or seg == RESERVED:
        return None
    return seg


def _registry_is_latest(entry):
    """True when the registry marked this concrete version the latest one."""
    meta = entry.get("_meta") if isinstance(entry, dict) else None
    off = (meta or {}).get("io.modelcontextprotocol.registry/official") or {}
    return bool(off.get("isLatest"))


def _version_key(v):
    """A sortable key from a version string — the run of integers it contains,
    as a tuple. "1.10.0" -> (1, 10, 0) sorts above "1.9.0". Non-numeric or empty
    versions collapse to (0,), the lowest."""
    parts = re.findall(r"\d+", str(v or ""))
    return tuple(int(p) for p in parts) if parts else (0,)


def _normalize_one_registry_server(server):
    """One registry `server` object -> a catalog-shaped dict, or None when it is
    not installable (no usable slug, no remote url, or an unknown package type)."""
    slug = _slug_from_registry_name(server.get("name"))
    if not slug:
        return None
    base = {
        "name": slug,
        "title": str(server.get("title") or "").strip(),
        "description": str(server.get("description") or "").strip(),
        "transport": "",
        "command": "",
        "args": [],
        "env_keys": [],
        "url": "",
    }

    # Remote wins when present: an http/sse endpoint needs no local launcher.
    remotes = server.get("remotes")
    if isinstance(remotes, list) and remotes and isinstance(remotes[0], dict):
        r = remotes[0]
        url = str(r.get("url") or "").strip()
        if not url:
            return None
        base["transport"] = "sse" if r.get("type") == "sse" else "http"
        base["url"] = url
        return base

    # Else a package server launched locally over stdio.
    packages = server.get("packages")
    if isinstance(packages, list) and packages and isinstance(packages[0], dict):
        p = packages[0]
        rtype = str(p.get("registryType") or "").strip().lower()
        command = _PKG_COMMAND.get(rtype)
        identifier = str(p.get("identifier") or "").strip()
        if not command or not identifier:
            return None  # a package we have no launcher for is not installable

        pkg_args = []
        for a in (p.get("packageArguments") or []):
            if isinstance(a, dict):
                val = a.get("value") or a.get("valueHint")
                if val:
                    pkg_args.append(str(val))

        if rtype == "npm":
            args = ["-y", identifier] + pkg_args
        elif rtype == "pypi":
            args = [identifier] + pkg_args
        else:  # oci
            args = ["run", "-i", "--rm", identifier]

        env_keys = [str(e["name"]) for e in (p.get("environmentVariables") or [])
                    if isinstance(e, dict) and e.get("name")]

        base["transport"] = "stdio"
        base["command"] = command
        base["args"] = args
        base["env_keys"] = env_keys
        return base

    return None  # neither remote nor a launchable package


def normalize_registry_servers(servers):
    """A registry response's `servers` list -> catalog-shaped results.

    Dedup by server.name keeping the isLatest row (else the highest version),
    then normalise each surviving server. Pure and network-free so a fabricated
    payload can be unit-tested without the wire."""
    if not isinstance(servers, list):
        return []

    best = {}  # server.name -> the winning entry
    for entry in servers:
        if not isinstance(entry, dict):
            continue
        server = entry.get("server")
        if not isinstance(server, dict):
            continue
        sname = server.get("name")
        if not isinstance(sname, str) or not sname:
            continue

        cur = best.get(sname)
        if cur is None:
            best[sname] = entry
            continue
        new_latest, cur_latest = _registry_is_latest(entry), _registry_is_latest(cur)
        if new_latest and not cur_latest:
            best[sname] = entry
        elif new_latest == cur_latest:  # same latest-status -> higher version wins
            if _version_key(server.get("version")) > \
                    _version_key(cur["server"].get("version")):
                best[sname] = entry

    out = []
    for entry in best.values():
        norm = _normalize_one_registry_server(entry.get("server") or {})
        if norm:
            out.append(norm)
    return out


def fetch_registry(q="", limit=20):
    """Fetch one page of the official registry and return its raw `servers`
    list. Adds &search only for a non-empty query; caps limit at 50 (default 20);
    6s timeout. Raises on any network/HTTP/parse error — the endpoint catches it
    and falls back to the built-in catalog, so this stays a thin, honest fetch."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(limit, 50))

    params = {"limit": str(limit)}
    if q:
        params["search"] = str(q)
    url = REGISTRY_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "sutra-ui-connectors"})
    with urllib.request.urlopen(req, timeout=REGISTRY_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    servers = data.get("servers") if isinstance(data, dict) else None
    return servers if isinstance(servers, list) else []


# ------------------------------------------------- import from ~/.claude.json ---
# The operator's global Claude config lists their own MCP servers under top-level
# `mcpServers` (the same dict Claude's `claude mcp add` writes). We read it
# fail-soft and normalise each entry to OUR connector model so the panel can
# offer them for one-click add. Nothing is saved here — the UI decides.


def _claude_json_path():
    """~/.claude.json, or SUTRA_UI_CLAUDE_JSON when set (tests point it at a
    tempfile). Resolved per call so a test's env override is honoured."""
    return Path(os.path.expanduser(
        os.environ.get("SUTRA_UI_CLAUDE_JSON", "~/.claude.json")))


def read_claude_mcp_servers():
    """The top-level `mcpServers` dict from ~/.claude.json, or {} on any
    missing/corrupt file or wrong shape. Never raises."""
    try:
        with open(_claude_json_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    mcp = data.get("mcpServers")
    return mcp if isinstance(mcp, dict) else {}


def normalize_claude_mcp_servers(mcp_servers):
    """A Claude `mcpServers` map (name -> spec) -> a list of connector-model
    dicts {name, transport, command, args, env, url, headers, enabled:false}.

    Transport is inferred from spec.type, else from the presence of a url
    (remote -> http) vs a command (stdio). Entries whose transport cannot be
    inferred, and any name colliding with the reserved "sutra", are skipped.
    Pure and network-free (unit-testable); the results are NOT persisted."""
    out = []
    if not isinstance(mcp_servers, dict):
        return out
    for name, spec in mcp_servers.items():
        if not isinstance(name, str) or not name or name == RESERVED:
            continue
        if not isinstance(spec, dict):
            continue

        t = str(spec.get("type", "") or "").strip().lower()
        url = str(spec.get("url", "") or "").strip()
        command = str(spec.get("command", "") or "").strip()

        if t in ("http", "sse", "stdio"):
            transport = t
        elif url:
            transport = "http"   # a url with no type -> remote (Claude's default)
        elif command:
            transport = "stdio"
        else:
            continue  # neither a url nor a command -> nothing we can launch

        args = [str(a) for a in (spec.get("args") or []) if isinstance(a, str)]

        env = {}
        if isinstance(spec.get("env"), dict):
            for k, v in spec["env"].items():
                if isinstance(k, str) and k.strip():
                    env[k] = "" if v is None else str(v)

        # headers only ride along on a remote transport, matching validate().
        headers = {}
        if transport in ("http", "sse") and isinstance(spec.get("headers"), dict):
            for k, v in spec["headers"].items():
                if isinstance(k, str) and k.strip():
                    headers[k] = "" if v is None else str(v)

        out.append({
            "name": name,
            "transport": transport,
            "command": command if transport == "stdio" else "",
            "args": args if transport == "stdio" else [],
            "env": env if transport == "stdio" else {},
            "url": url if transport in ("http", "sse") else "",
            "headers": headers,
            "enabled": False,
        })
    return out
