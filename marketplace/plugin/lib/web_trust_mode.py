#!/usr/bin/env python3
"""
web_trust_mode.py - WebFetch / WebSearch URL classifier for permission-gate v2.32+

BUILD-LAYER: L0 (fleet)
Charter: sutra/os/charters/PERMISSIONS.md Tier 1.9 (Web Trust Mode)

Threat model: same as Bash Trust Mode - single trusted local operator on a
personally managed machine. Network reads to public URLs are auto-approved;
internal/metadata/private endpoints prompt to defend against SSRF-style
information leak (cloud-metadata service, private LAN scan, file:// reads).

Reads PermissionRequest JSON on stdin. Prints one JSON line:
  {"prompt": false, "pattern": "WebFetch(domain:<host>)"}  -> auto-allow
  {"prompt": true,  "category": "...", "reason": "..."}    -> prompt

Deny-list (always prompts):
  - localhost / 127.0.0.0/8 / 0.0.0.0
  - ::1 (IPv6 loopback) / fc00::/7 (ULA) / fe80::/10 (link-local)
  - 169.254.0.0/16 (link-local + AWS/GCP/Azure metadata service)
  - 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 (RFC1918 private)
  - file://, ftp://, gopher://, dict://, ldap://, tftp://

Fail-safe-to-prompt: any parse error / unknown shape -> prompt=true.
"""
from __future__ import annotations

import ipaddress
import json
import sys
from urllib.parse import urlparse


PROMPT_SCHEMES = frozenset({
    "file", "ftp", "gopher", "dict", "ldap", "tftp", "jar",
})

LOOPBACK_HOSTS = frozenset({
    "localhost", "ip6-localhost", "ip6-loopback",
})


def _ip_is_internal(host: str) -> bool:
    """True if `host` parses as a loopback / private / link-local / reserved IP."""
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )


def classify_url(url: str):
    """Return (prompt: bool, category: str, reason: str)."""
    if not url:
        return (True, "empty-url", "empty url")

    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()

    if scheme in PROMPT_SCHEMES:
        return (True, "non-http-scheme",
                f"scheme '{scheme}' not auto-approved")

    if scheme not in {"http", "https"}:
        return (True, "unknown-scheme",
                f"scheme '{scheme}' not in http/https")

    if not host:
        return (True, "no-host", "url has no host")

    if host in LOOPBACK_HOSTS:
        return (True, "loopback-host", f"hostname '{host}' is loopback")

    if _ip_is_internal(host):
        return (True, "private-ip",
                f"ip '{host}' is loopback/private/link-local/reserved")

    return (False, "web-public", f"public url to {host}")


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"prompt": True, "category": "no-input",
                          "reason": "empty stdin"}))
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"prompt": True, "category": "malformed-input",
                          "reason": f"json parse error: {exc}"}))
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name == "WebSearch":
        # No URL involved (search-engine query); auto-approve unconditionally.
        print(json.dumps({"prompt": False, "pattern": "WebSearch",
                          "reason": "search-engine query"}))
        return 0

    url = tool_input.get("url") or ""
    prompt, category, reason = classify_url(url)
    if prompt:
        print(json.dumps({"prompt": True, "category": category,
                          "reason": reason}))
    else:
        host = urlparse(url).hostname or ""
        print(json.dumps({"prompt": False,
                          "pattern": f"WebFetch(domain:{host})",
                          "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
