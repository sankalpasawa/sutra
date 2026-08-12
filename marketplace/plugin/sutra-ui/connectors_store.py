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
      "command": str, "args": [str], "env": {k: v}, "url": str, "enabled": bool }

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

    return {
        "id": str(raw.get("id", "") or "").strip(),
        "name": name,
        "transport": transport,
        "command": command,
        "args": args,
        "env": env,
        "url": url,
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
        http/sse -> {"type": "http"|"sse", "url"}

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
            out[name] = {"type": transport, "url": conn["url"]}
    return out
