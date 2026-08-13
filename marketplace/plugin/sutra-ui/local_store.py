"""The LOCAL connector — 1MCP aggregating every local MCP server, assorted.

WHY A SECOND CONNECTOR
----------------------
composio_store.py gave the panel Composio's 1181 hosted toolkits behind one
remote endpoint. It cannot give it `filesystem`, `git`, `playwright` or
`sqlite`: those are LOCAL servers that run as a process on this machine, and
Composio is a hosted API for cloud SaaS. Those two things are different in kind,
so they are two connectors rather than one leaky abstraction:

    connector   backend                          catalog
    ---------   ------------------------------   ---------------------------
    composio    a hosted tool router session     ComposioHQ/composio
    local       a local 1MCP aggregator process  the open MCP Registry

WHAT 1MCP IS, AND WHY IT AND NOT THE ALTERNATIVES
-------------------------------------------------
1MCP (`@1mcp/agent`, Apache-2.0, 1mcp-app/agent) is an MCP aggregator: it fronts
many MCP servers and presents them as ONE. Run as
`1mcp serve --transport=stdio`, it is a single stdio process the Claude CLI
spawns per turn exactly like any other stdio server — no daemon to supervise,
no port to own, nothing left running when the turn ends.

That last property is why it and not MetaMCP, which is the better-known
aggregator: MetaMCP wants Docker, Postgres and its own Next.js UI, all of which
this panel would then have to install, supervise and duplicate. `1mcp proxy`
was also rejected — it requires a separate long-lived `1mcp serve` to proxy TO,
which is the daemon we are avoiding. `serve --transport=stdio` has no such
dependency.

WITHOUT the aggregator, N enabled local servers means N entries in every turn's
--mcp-config and N tool namespaces in the model's context. WITH it, one entry
and one namespace, however many servers are behind it.

WHAT "ASSORTED" MEANS HERE, PRECISELY
-------------------------------------
Every server carries a `tag` — 1MCP's own per-server field, described upstream
as "Tags for filtering and organizing servers". It is real config, not a UI
decoration: the screen groups by it, and it is what `--filter` narrows on.

The tag is a CATEGORY, and the categories are Composio's, looked up by slug in
the catalog composio_store already mirrors. That is deliberate: `github` is
"developer tools" in BOTH connectors, so the two halves of the Connectors screen
assort into one taxonomy instead of two that nearly agree. When a slug is not in
Composio's catalog, `_guess_category` applies a keyword heuristic over the
title and description — and it is a HEURISTIC, labelled as one, overridable per
server, never presented as registry metadata. The open MCP Registry publishes no
category field; inventing one and calling it upstream's would be a lie.

WHAT AUTO-UPDATES
-----------------
Same three-way split composio_store documents, because the same three claims
hide in "it updates":

  THE SERVERS THEMSELVES — a server publishes a new version.
      Nothing here updates. Every stdio server is launched through `npx -y` /
      `uvx`, which resolve the current published version at spawn time.

  THE REGISTRY — a new server is published to registry.modelcontextprotocol.io.
      Searched live, and the first page is TTL-cached so browsing is free.
      Latency: immediate on search, <= REGISTRY_TTL for the default page.

  THE AGGREGATOR — 1mcp-app/agent ships a release.
      The launch command PINS a version (an unpinned `npx -y @1mcp/agent` would
      silently change the aggregator under a running install). The pin is
      refreshed from npm's `latest` dist-tag on the same TTL-gated check the
      Composio catalog uses, so the desktop app tracks upstream without ever
      running an unreviewed floating version mid-session.

STORE
-----
~/.sutra-ui/local.json:

    {"servers": [{id, name, title, tag, transport, command, args, env,
                  url, headers, enabled}],
     "filter": str, "route_composio": bool,
     "agent": {"version": str, "checked_at": float}}

1MCP's own config is DERIVED, never hand-kept: rewritten from this store on
every mutation to ~/.sutra-ui/1mcp/mcp.json. One source of truth, and deleting
the derived file costs one mutation to regenerate.

Fail-soft and atomic on the same terms as composio_store; SUTRA_UI_LOCAL and
SUTRA_UI_1MCP_DIR repoint the files for tests.
"""
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import composio_store as cx

# ------------------------------------------------------------- constants ----
# The aggregator. Pinned by version, never floating — see the module docstring.
AGENT_PKG = "@1mcp/agent"
# The fallback pin: what shipped with this build, used until a check succeeds.
# Bumped by refresh_agent(), not by hand.
AGENT_FALLBACK_VERSION = "0.34.4"
NPM_LATEST_URL = "https://registry.npmjs.org/%s/latest" % urllib.parse.quote(
    AGENT_PKG, safe="")

# The official open registry. v0.1 is the shape this normaliser targets; a
# version bump upstream is a code change here, not a silent misparse.
REGISTRY_URL = os.environ.get(
    "SUTRA_UI_MCP_REGISTRY", "https://registry.modelcontextprotocol.io/v0.1/servers")

NET_TIMEOUT = 10
REGISTRY_TTL = 6 * 3600      # the default (unsearched) page
AGENT_TTL = 24 * 3600        # how often to look for a newer aggregator

# name: the key a server takes inside 1MCP's config. Same DNS-ish token the
# panel used before, because it is also what appears in tool namespaces.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,38}$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}$")
TRANSPORTS = ("stdio", "http", "sse")
# Reserved keys in the merged --mcp-config. A local server may take none of
# them: "sutra" is the panel's own server, "composio" is the hosted connector,
# and "local" is THIS aggregator.
RESERVED = ("sutra", "composio", "local")
SERVER_NAME = "local"
MAX_SERVERS = 32

# registryType -> the launcher a stdio package server runs under.
_PKG_COMMAND = {"npm": "npx", "pypi": "uvx", "oci": "docker"}

STORE_PATH = Path(os.path.expanduser(
    os.environ.get("SUTRA_UI_LOCAL", "~/.sutra-ui/local.json")))
ONEMCP_DIR = Path(os.path.expanduser(
    os.environ.get("SUTRA_UI_1MCP_DIR", "~/.sutra-ui/1mcp")))
REGISTRY_CACHE = Path(os.path.expanduser(
    os.environ.get("SUTRA_UI_MCP_REGISTRY_CACHE", "~/.sutra-ui/mcp-registry.json")))

# ------------------------------------------------------------ categories ----
# The fallback taxonomy, used ONLY when a slug is absent from Composio's
# catalog. Ordered: the first keyword that matches wins, so the specific
# patterns come before the general ones. Keys are the tag emitted.
_CATEGORY_HINTS = [
    ("developer-tools", ("git", "github", "gitlab", "code", "repo", "lint",
                         "compile", "debug", "ide", "terminal", "shell",
                         "kubernetes", "docker", "deploy", "ci/cd")),
    ("databases", ("sql", "postgres", "mysql", "sqlite", "mongo", "redis",
                   "database", "duckdb", "clickhouse", "neo4j")),
    ("browser-automation", ("browser", "playwright", "puppeteer", "chrome",
                            "selenium", "scrape", "crawl")),
    ("search", ("search", "web search", "index", "retrieval", "rag")),
    ("filesystem", ("filesystem", "file system", "files", "directory", "disk")),
    ("communication", ("slack", "discord", "email", "gmail", "chat",
                       "message", "sms", "telegram")),
    ("productivity", ("notion", "calendar", "task", "todo", "note",
                      "document", "sheet", "jira", "linear", "asana")),
    ("monitoring", ("monitor", "log", "metric", "trace", "observability",
                    "sentry", "grafana", "alert")),
    ("artificial-intelligence", ("llm", "model", "embedding", "openai",
                                 "anthropic", "hugging face", "inference",
                                 "prompt", "agent")),
    ("memory", ("memory", "knowledge graph", "recall", "context")),
]
DEFAULT_CATEGORY = "other"


def _slug_category(slug, title="", description=""):
    """The tag for one server: Composio's category when the slug is one of its
    toolkits, else a keyword guess, else "other".

    Returns (tag, source) so a caller can tell a LOOKED-UP category from a
    GUESSED one — the screen says which, because a guess presented as fact is
    the kind of small lie that erodes a catalog's credibility."""
    slug = str(slug or "").strip().lower()
    try:
        for row in (cx._catalog_file()[0].get("toolkits") or []):
            if row.get("slug") == slug:
                return _slugify_tag(row.get("category")), "composio"
    except Exception:
        pass  # a broken Composio catalog must not break local categorisation
    return _guess_category(slug, title, description), "guess"


def _guess_category(*parts):
    """The keyword heuristic. Pure and network-free so its judgements are
    testable, and deliberately conservative: no match is "other", not a
    confident wrong answer.

    The NAME is one of the parts, and load-bearing. The add form leaves title
    and description blank, so a heuristic reading only those two filed `git` and
    `filesystem` — the two most obvious cases in the table below — under "other".
    A server's name is usually the strongest signal it has."""
    hay = " ".join(str(p or "") for p in parts).lower()
    for tag, words in _CATEGORY_HINTS:
        for w in words:
            if w in hay:
                return tag
    return DEFAULT_CATEGORY


def _slugify_tag(value):
    """A category string -> a 1MCP tag. "developer tools" -> "developer-tools"."""
    tag = re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")[:39]
    return tag if TAG_RE.match(tag) else DEFAULT_CATEGORY


# ------------------------------------------------------------------ io ------
def _new_id():
    return "lx_" + uuid.uuid4().hex[:12]


def validate(raw):
    """Normalise one local server, or raise ValueError with a clear message.

    Same contract the panel's connector validator always had — name/transport
    rules, args and env sanitised, headers only on a remote transport — plus a
    `tag`, which is what makes the set assortable. The id is preserved when
    given but not generated here; add_or_update owns id lifecycle."""
    if not isinstance(raw, dict):
        raise ValueError("server must be an object")

    name = str(raw.get("name", "")).strip().lower()
    if not NAME_RE.match(name):
        raise ValueError(
            "name must match ^[a-z0-9][a-z0-9_-]{0,38}$ — a lowercase letter or "
            "digit, then letters/digits/underscore/hyphen, at most 39 characters")
    if name in RESERVED:
        raise ValueError('name "%s" is reserved' % name)

    transport = str(raw.get("transport", "")).strip()
    if transport not in TRANSPORTS:
        raise ValueError("transport must be one of: %s" % ", ".join(TRANSPORTS))

    command = str(raw.get("command", "") or "").strip()
    url = str(raw.get("url", "") or "").strip()
    if transport == "stdio" and not command:
        raise ValueError("stdio transport requires a command")
    if transport in ("http", "sse") and not url:
        raise ValueError("%s transport requires a url" % transport)

    # args: strings only. A non-string is DROPPED, never stringified — passing
    # the text "None" to a subprocess is worse than passing nothing.
    args = [str(a) for a in (raw.get("args") or []) if isinstance(a, str)]

    # env: str->str. A blank value is KEPT — "added from the registry, secret
    # not yet filled" is a real state the screen needs to show.
    env = {}
    if isinstance(raw.get("env"), dict):
        for k, v in raw["env"].items():
            if isinstance(k, str) and k.strip():
                env[k] = "" if v is None else str(v)

    headers = {}
    if transport in ("http", "sse") and isinstance(raw.get("headers"), dict):
        for k, v in raw["headers"].items():
            if isinstance(k, str) and k.strip():
                headers[k] = "" if v is None else str(v)

    title = str(raw.get("title", "") or "").strip()[:120]
    tag = _slugify_tag(raw.get("tag")) if raw.get("tag") else \
        _slug_category(name, title, raw.get("description", ""))[0]

    return {
        "id": str(raw.get("id", "") or "").strip(),
        "name": name,
        "title": title or name,
        "tag": tag,
        "transport": transport,
        "command": command,
        "args": args,
        "env": env,
        "url": url,
        "headers": headers,
        "enabled": bool(raw.get("enabled", True)),
    }


def _blank():
    return {"servers": [], "filter": "", "route_composio": False,
            "agent": {"version": AGENT_FALLBACK_VERSION, "checked_at": 0.0}}


def load():
    """The whole store. Fail-soft: a missing or corrupt file, or a hand-edited
    bad row, yields as much as is parseable — one bad server is dropped rather
    than losing the set."""
    raw = cx._read_json(STORE_PATH, {})
    out = _blank()
    for row in (raw.get("servers") or [])[:MAX_SERVERS]:
        try:
            srv = validate(row)
        except ValueError:
            continue
        if not srv["id"]:
            srv["id"] = _new_id()
        out["servers"].append(srv)

    out["filter"] = str(raw.get("filter", "") or "").strip()[:200]
    out["route_composio"] = bool(raw.get("route_composio"))
    agent = raw.get("agent") if isinstance(raw.get("agent"), dict) else {}
    version = str(agent.get("version") or "").strip()
    out["agent"] = {
        "version": version if _VERSION_RE.match(version) else AGENT_FALLBACK_VERSION,
        "checked_at": float(agent.get("checked_at") or 0),
    }
    return out


_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def save(store):
    """Write the store AND re-derive 1MCP's config from it. The two must never
    be written apart: a store that says a server is enabled while mcp.json does
    not list it is a panel that lies about what the next turn can reach."""
    cx._write_json(STORE_PATH, store)
    write_1mcp_config(store)
    return store


# ------------------------------------------------------------- mutators -----
def add_or_update(raw):
    """Validate and upsert one server; returns the stored dict.

    Name uniqueness is enforced (excluding self): 1MCP keys servers by name, so
    two servers sharing one would silently drop one — better a clear 400 than a
    server that vanished."""
    srv = validate(raw)
    store = load()

    for other in store["servers"]:
        if other["name"] == srv["name"] and other["id"] != srv["id"]:
            raise ValueError('a server named "%s" already exists' % srv["name"])

    if not srv["id"]:
        srv["id"] = _new_id()
        if len(store["servers"]) >= MAX_SERVERS:
            raise ValueError(
                "at most %d local servers — remove one first" % MAX_SERVERS)

    for i, other in enumerate(store["servers"]):
        if other["id"] == srv["id"]:
            store["servers"][i] = srv
            break
    else:
        store["servers"].append(srv)

    save(store)
    return srv


def toggle(sid):
    """Flip `enabled` for one server. Returns the updated dict, or None when no
    server matches (the endpoint maps None -> 404)."""
    store = load()
    for i, srv in enumerate(store["servers"]):
        if srv["id"] == sid:
            srv["enabled"] = not srv.get("enabled", False)
            store["servers"][i] = srv
            save(store)
            return srv
    return None


def remove(sid):
    """Delete one server. True if one was removed, else False."""
    store = load()
    kept = [s for s in store["servers"] if s["id"] != sid]
    if len(kept) == len(store["servers"]):
        return False
    store["servers"] = kept
    save(store)
    return True


def retag(sid, tag):
    """Move one server to another category. The tag is the operator's to set —
    a guessed category that is wrong should be fixable in one click, not an
    argument with the heuristic."""
    store = load()
    for i, srv in enumerate(store["servers"]):
        if srv["id"] == sid:
            srv["tag"] = _slugify_tag(tag)
            store["servers"][i] = srv
            save(store)
            return srv
    return None


def set_options(filter_=None, route_composio=None):
    """The two knobs that change what the aggregator exposes rather than what
    is in it: a tag filter, and whether the hosted connector is routed through
    here too. Returns state()."""
    store = load()
    if filter_ is not None:
        # Only tags, commas and 1MCP's boolean operators. Anything else would
        # be pasted straight into an argv slot.
        f = str(filter_).strip()[:200]
        if f and not re.match(r"^[a-z0-9 ,\-_()+&|!]*$", f, re.I):
            raise ValueError(
                "filter may contain tag names, commas and the operators + & | ! ( )")
        store["filter"] = f
    if route_composio is not None:
        store["route_composio"] = bool(route_composio)
    save(store)
    return state()


# ------------------------------------------------------- 1MCP config out ----
def config_path():
    return ONEMCP_DIR / "mcp.json"


def onemcp_servers(store=None):
    """The ENABLED servers in 1MCP's `mcpServers` shape.

    1MCP accepts the same {command,args,env} / {url,headers} pair the rest of
    the MCP world uses, PLUS `tags` — which is the whole reason the assorting is
    real config rather than a label this panel keeps to itself.

    When `route_composio` is on, the hosted connector is written in here as one
    more tagged remote server, so a single aggregated endpoint carries local
    servers AND Composio's toolkits. Off by default: it puts an npx process in
    front of an endpoint that works without one, and that is a trade the
    operator should make deliberately."""
    store = store or load()
    out = {}
    for srv in store["servers"]:
        if not srv.get("enabled"):
            continue
        name = srv["name"]
        if name in RESERVED:
            continue  # defensive; validate already rejects these
        if srv["transport"] == "stdio":
            if not srv["command"]:
                continue
            out[name] = {"command": srv["command"], "args": list(srv["args"]),
                         "env": dict(srv["env"]), "tags": [srv["tag"]]}
        else:
            if not srv["url"]:
                continue
            spec = {"type": srv["transport"], "url": srv["url"],
                    "tags": [srv["tag"]]}
            if srv["headers"]:
                spec["headers"] = dict(srv["headers"])
            out[name] = spec

    if store.get("route_composio"):
        for name, spec in _composio_fragment().items():
            out[name] = dict(spec, tags=["hosted"])
    return out


def _composio_fragment():
    """Composio's server spec, or {}. Wrapped so a hosted-connector failure
    degrades the aggregator's contents rather than failing the config write."""
    try:
        return cx.mcp_servers_fragment()
    except Exception:
        return {}


def write_1mcp_config(store=None):
    """Render 1MCP's mcp.json from the store. Derived, never hand-kept.

    `serverDefaults` is written empty rather than omitted: 1MCP's own default
    config carries the key, and matching its shape means a file this panel wrote
    is one the `1mcp` CLI can also read and edit without a migration."""
    store = store or load()
    cx._write_json(config_path(), {
        "$schema": "https://raw.githubusercontent.com/1mcp-app/agent/main/"
                   "schemas/mcp-config.schema.json",
        "serverDefaults": {},
        "mcpServers": onemcp_servers(store),
    })
    return config_path()


# ------------------------------------------------------------- preflight ----
def preflight():
    """Can this machine actually run the aggregator? Two independent facts,
    reported separately, in the shape providers.py established:

        npx      the launcher `1mcp serve` is spawned through
        node     what it runs on

    A connector that says "enabled" on a machine with no Node is the failure
    this exists to prevent — it would surface as a turn where the tools simply
    are not there, with nothing on screen explaining why."""
    npx = shutil.which("npx")
    node = shutil.which("node")
    return {
        "npx": npx or "",
        "node": node or "",
        "runnable": bool(npx and node),
        "reason": "" if (npx and node) else
                  ("`npx` is not on PATH" if not npx else "`node` is not on PATH"),
    }


# --------------------------------------------------------------- state ------
def state():
    """Everything the panel needs to render the local half of the screen,
    already assorted: servers grouped by tag, in a stable order."""
    store = load()
    groups = {}
    for srv in store["servers"]:
        groups.setdefault(srv["tag"], []).append(srv)
    return {
        "servers": store["servers"],
        "groups": [{"tag": t, "servers": groups[t]} for t in sorted(groups)],
        "enabled_count": sum(1 for s in store["servers"] if s["enabled"]),
        "filter": store["filter"],
        "route_composio": store["route_composio"],
        "agent": {
            "package": AGENT_PKG,
            "version": store["agent"]["version"],
            "checked_at": store["agent"]["checked_at"],
            "ttl": AGENT_TTL,
        },
        "preflight": preflight(),
        "config_path": str(config_path()),
    }


# ------------------------------------------------------ aggregator update ---
def agent_is_stale():
    return (time.time() - load()["agent"]["checked_at"]) > AGENT_TTL


def refresh_agent(force=False):
    """Adopt npm's `latest` for the aggregator. Never raises.

    The pin exists so a running install cannot have its aggregator swapped
    mid-session by an `npx -y` resolving something new; this is how the pin
    moves — deliberately, on a TTL, with the version recorded in the store."""
    store = load()
    if not force and not agent_is_stale():
        return {"checked": False, "updated": False, "reason": "fresh",
                "version": store["agent"]["version"]}

    try:
        status, payload, _ = cx._http_json("GET", NPM_LATEST_URL,
                                           timeout=NET_TIMEOUT)
    except Exception as exc:
        return {"checked": True, "updated": False,
                "error": _net_message(exc, NPM_LATEST_URL),
                "version": store["agent"]["version"]}

    if status != 200 or not isinstance(payload, dict):
        return {"checked": True, "updated": False,
                "error": "npm returned HTTP %s" % status,
                "version": store["agent"]["version"]}

    version = str(payload.get("version") or "").strip()
    if not _VERSION_RE.match(version):
        return {"checked": True, "updated": False,
                "error": "npm returned an unusable version: %r" % version[:40],
                "version": store["agent"]["version"]}

    before = store["agent"]["version"]
    store["agent"] = {"version": version, "checked_at": time.time()}
    save(store)
    return {"checked": True, "updated": version != before,
            "from": before, "version": version}


def _net_message(exc, url):
    if isinstance(exc, urllib.error.URLError) and getattr(exc, "reason", None):
        return "could not reach %s (%s)" % (
            urllib.parse.urlsplit(url).netloc, exc.reason)
    return str(exc) or exc.__class__.__name__


# ------------------------------------------------------------- registry -----
def _slug_from_registry_name(full_name):
    """A valid server `name` from a registry server.name like
    "io.github.owner/my-server": the last '/'-segment, lowercased, anything
    outside [a-z0-9_-] mapped to '-', leading non-alphanumerics stripped, capped
    at 39. None when nothing valid survives or it would collide with a reserved
    key."""
    seg = str(full_name or "").rsplit("/", 1)[-1].lower()
    seg = re.sub(r"[^a-z0-9_-]", "-", seg)
    seg = re.sub(r"^[^a-z0-9]+", "", seg)[:39]
    if not NAME_RE.match(seg) or seg in RESERVED:
        return None
    return seg


def _registry_is_latest(entry):
    meta = entry.get("_meta") if isinstance(entry, dict) else None
    off = (meta or {}).get("io.modelcontextprotocol.registry/official") or {}
    return bool(off.get("isLatest"))


def _version_key(v):
    """A sortable key from a version string — the integers it contains.
    "1.10.0" -> (1, 10, 0) sorts above "1.9.0"; anything else is (0,)."""
    parts = re.findall(r"\d+", str(v or ""))
    return tuple(int(p) for p in parts) if parts else (0,)


def _normalize_one(server):
    """One registry `server` -> an add-ready row, or None when it is not
    installable (no usable slug, no url, or a package type we have no launcher
    for). Carries the assorted `tag` and how it was decided."""
    slug = _slug_from_registry_name(server.get("name"))
    if not slug:
        return None
    title = str(server.get("title") or "").strip()
    description = str(server.get("description") or "").strip()
    tag, tag_source = _slug_category(slug, title, description)
    base = {"name": slug, "title": title or slug, "description": description,
            "tag": tag, "tag_source": tag_source, "transport": "",
            "command": "", "args": [], "env_keys": [], "url": ""}

    # A remote wins when present: an endpoint needs no local launcher.
    remotes = server.get("remotes")
    if isinstance(remotes, list) and remotes and isinstance(remotes[0], dict):
        r = remotes[0]
        url = str(r.get("url") or "").strip()
        if not url:
            return None
        base["transport"] = "sse" if r.get("type") == "sse" else "http"
        base["url"] = url
        return base

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

        base["transport"] = "stdio"
        base["command"] = command
        base["args"] = args
        base["env_keys"] = [str(e["name"]) for e in
                            (p.get("environmentVariables") or [])
                            if isinstance(e, dict) and e.get("name")]
        return base

    return None  # neither remote nor a launchable package


def normalize_registry(servers):
    """A registry response's `servers` list -> add-ready rows.

    Dedup by server.name keeping the isLatest row (else the highest version),
    then normalise. Pure and network-free, so a fabricated payload is testable
    without the wire."""
    if not isinstance(servers, list):
        return []

    best = {}
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
        elif new_latest == cur_latest and \
                _version_key(server.get("version")) > \
                _version_key(cur["server"].get("version")):
            best[sname] = entry

    out = []
    for entry in best.values():
        row = _normalize_one(entry.get("server") or {})
        if row:
            out.append(row)
    out.sort(key=lambda r: (r["tag"], r["name"]))
    return out


def fetch_registry(q="", limit=24):
    """One page of the registry, raw. Raises on any network/HTTP/parse error —
    the caller decides what a failure means, so this stays an honest fetch."""
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 24
    params = {"limit": str(limit)}
    if q:
        params["search"] = str(q)
    status, payload, _ = cx._http_json(
        "GET", REGISTRY_URL + "?" + urllib.parse.urlencode(params),
        timeout=NET_TIMEOUT)
    if status != 200 or not isinstance(payload, dict):
        raise RuntimeError("registry returned HTTP %s" % status)
    servers = payload.get("servers")
    return servers if isinstance(servers, list) else []


def browse(q="", limit=24):
    """Search the registry, assorted, with the default page TTL-cached.

    A SEARCH always goes to the wire — a cached search is a stale answer to a
    question the operator just asked. The EMPTY query is the browse view, hit on
    every screen open, so it is cached: that is the one that would otherwise
    make opening the screen cost a request every time.

    Never raises: on any failure it returns the last good page it has, with the
    error alongside, so a registry outage degrades to a stale catalog rather
    than an empty screen."""
    q = str(q or "").strip()
    if not q:
        cached = cx._read_json(REGISTRY_CACHE, {})
        rows = cached.get("results")
        fresh = (time.time() - float(cached.get("fetched_at") or 0)) < REGISTRY_TTL
        if isinstance(rows, list) and rows and fresh:
            return {"results": rows, "source": "cache",
                    "fetched_at": cached.get("fetched_at", 0)}

    try:
        rows = normalize_registry(fetch_registry(q, limit))
    except Exception as exc:
        cached = cx._read_json(REGISTRY_CACHE, {})
        return {"results": cached.get("results") or [], "source": "stale",
                "fetched_at": cached.get("fetched_at", 0),
                "error": _net_message(exc, REGISTRY_URL)}

    if not q:
        cx._write_json(REGISTRY_CACHE,
                       {"results": rows, "fetched_at": time.time()})
    return {"results": rows, "source": "registry", "fetched_at": time.time()}


# --------------------------------------------------------------- merge ------
def mcp_servers_fragment():
    """The aggregator as {name: server_spec} for app._sutra_mcp_config:

        {"local": {"command": "npx",
                   "args": ["-y", "@1mcp/agent@<pinned>", "serve",
                            "--transport=stdio", "--config", <path>]}}

    ONE stdio process, however many servers are behind it. `{}` when nothing is
    enabled or the machine cannot run it, so the caller splats unconditionally.

    The version is PINNED into the argv. `npx -y @1mcp/agent` without one would
    resolve whatever npm calls latest at spawn time, which means the aggregator
    fronting every local tool could change between two turns of the same
    session with nothing recorded anywhere.

    FAIL-SOFT BY CONTRACT, like the hosted connector: this runs on the hot path
    of every turn, so anything unexpected returns {} rather than raising."""
    try:
        store = load()
        if not any(s["enabled"] for s in store["servers"]) and \
                not store.get("route_composio"):
            return {}
        if not preflight()["runnable"]:
            return {}
        # The config is derived, so re-render it here too: a store edited by
        # hand (or a deleted mcp.json) must not hand the aggregator a stale set.
        write_1mcp_config(store)

        args = ["-y", "%s@%s" % (AGENT_PKG, store["agent"]["version"]),
                "serve", "--transport=stdio", "--config", str(config_path())]
        if store["filter"]:
            args += ["--filter", store["filter"]]
        return {SERVER_NAME: {"command": "npx", "args": args, "env": {}}}
    except Exception:
        return {}
