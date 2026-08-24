"""Which third-party account a Claude-held connector is bound to.

WHY THIS EXISTS, AND WHY IT LOOKED IMPOSSIBLE

Nothing on this machine records it. The per-connector Keychain entry has an
EMPTY access token; Claude's desktop store has no account field; and
GET /v1/mcp_servers returns fifteen fields, none of them an account. Measured,
not assumed -- see ADR-035.

The credential is not local because it does not need to be: Anthropic's MCP
proxy holds it. So the account is not read out of a token, it is obtained by
ASKING THE CONNECTOR, through the proxy, using the operator's own Claude
session token -- the same token, the same endpoint and the same request the
`claude` CLI already makes on every `mcp list`.

THIS READS ANOTHER APPLICATION'S CREDENTIAL. ADR-035 decision 3 said Sutra
would not. That decision is amended by founder direction (2026-08-24): "let's
focus on reading and getting the account details directly through token".
The token is read, used for one HTTPS request, and never stored, logged,
returned in any payload, or written anywhere.

WHAT IS AND IS NOT RESOLVABLE

There is no whoami tool on any of these servers, so identity is inferred from
the cheapest authoritative artefact each connector exposes:

  Gmail   the sender of the operator's own sent mail. Metadata-only view --
          no subject, no snippet, no body is requested or received.
  others  NOT RESOLVABLE yet, and reported that way. Google Drive would need a
          file-owner lookup, which means touching file metadata; Atlassian Rovo
          needs authentication first. Neither is guessed.

The failure mode that matters is not "no answer" -- it is a CONFIDENT WRONG
answer. ~/.claude.json holds the CLAUDE account email, which on many machines
is also a @gmail.com address, so a plausible wrong value is always within
reach. Every path here either returns an address the CONNECTOR reported, or
returns None.
"""

import json
import subprocess
import urllib.error
import urllib.request
import uuid

MCP_PROXY = "https://mcp-proxy.anthropic.com/v1/mcp/%s"
SERVERS_URL = "https://api.anthropic.com/v1/mcp_servers?limit=1000"
SERVERS_BETA = "mcp-servers-2025-12-04"

# Cloudflare rejects an unrecognised agent with a 403 before the API is reached,
# so this is required rather than cosmetic. Discovered by getting the 403.
_UA = "claude-cli/2.1.212 (external, cli)"
TIMEOUT = 20


def _session_token():
    """The operator's Claude session token, or None.

    Read at the moment of use and never retained. `security` is used rather
    than Security.framework because the item's ACL already permits any process
    of this user -- and the service name, not a secret, is what lands in argv.
    """
    try:
        raw = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=TIMEOUT).stdout.strip()
        tok = (json.loads(raw).get("claudeAiOauth") or {}).get("accessToken") or ""
        return tok or None
    except Exception:
        return None


def _post(url, token, payload, session_id):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": _UA,
        # Undocumented and REQUIRED -- the proxy 400s without it.
        "X-Mcp-Client-Session-Id": session_id,
    })
    return urllib.request.urlopen(req, timeout=TIMEOUT).read().decode("utf-8", "replace")


def _rpc_result(body):
    """The proxy answers as SSE (`event: message\\ndata: {...}`) even for a
    single reply, so the JSON has to be lifted out of the data line."""
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            line = line[6:]
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def server_ids(token):
    """{display_name: server_id} for the operator's connectors, or {}."""
    try:
        req = urllib.request.Request(SERVERS_URL, headers={
            "Authorization": "Bearer " + token,
            "anthropic-beta": SERVERS_BETA,
            "anthropic-version": "2023-06-01",
            "User-Agent": _UA,
        })
        data = json.load(urllib.request.urlopen(req, timeout=TIMEOUT)).get("data") or []
        return {s.get("display_name"): s.get("id") for s in data if s.get("id")}
    except Exception:
        return {}


def _call_tool(token, server_id, name, arguments):
    sid = str(uuid.uuid4())
    url = MCP_PROXY % server_id
    _post(url, token, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "sutra", "version": "1"}}}, sid)
    body = _post(url, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": name, "arguments": arguments}}, sid)
    return _rpc_result(body)


def _gmail_account(token, server_id):
    """The operator's own address, from the sender of their own sent mail.

    METADATA_ONLY is not an optimisation, it is the point: that view returns
    sender/recipients/date and omits subject, snippet and body, so determining
    an address never reads the content of a message.
    """
    res = _call_tool(token, server_id, "search_threads",
                     {"query": "in:sent", "pageSize": 1,
                      "view": "THREAD_VIEW_METADATA_ONLY"})
    if not res:
        return None
    try:
        payload = json.loads(res["result"]["content"][0]["text"])
        threads = payload.get("threads") or []
        for t in threads:
            for m in (t.get("messages") or []):
                s = (m.get("sender") or "").strip()
                if "@" in s:
                    return s
    except Exception:
        pass
    # The shape moved. Do NOT pattern-match an address out of the response and
    # present it as the account: every Gmail reply is full of OTHER people's
    # addresses, so the first match is most likely the person last emailed.
    return None


#: Only connectors with an authoritative, cheap, metadata-only identity source.
#: An entry is added when its path is PROVEN, never on the assumption that one
#: probably exists.
RESOLVERS = {"gmail": ("Gmail", _gmail_account)}


def resolve(keys):
    """{catalogue_key: address-or-None} for the keys that have a resolver.

    A key with no resolver is absent from the result entirely, which the caller
    renders as "not resolvable" -- distinct from a resolver that ran and found
    nothing, which is None.
    """
    wanted = [k for k in keys if k in RESOLVERS]
    if not wanted:
        return {}
    token = _session_token()
    if not token:
        return {}
    ids = server_ids(token)
    out = {}
    for key in wanted:
        display, fn = RESOLVERS[key]
        sid = ids.get(display)
        if not sid:
            continue
        try:
            out[key] = fn(token, sid)
        except Exception:
            out[key] = None          # asked and could not tell -- never a guess
    return out
