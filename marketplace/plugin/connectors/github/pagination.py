"""Link-header pagination and opaque cursors.

Two rules, both from design 03 §3.4:

  Follow `Link: rel="next"`. NEVER construct `?page=n` -- constructed page
  numbers skip and duplicate entries when the underlying set changes mid-walk,
  and they do not work at all on cursor-paginated endpoints.

  A cursor handed to a client is SIGNED and its URL is re-validated against the
  connector's own api_base before it is ever dereferenced. An unsigned cursor
  that wraps a URL is a request to point our authenticated client wherever the
  caller likes (threat T-17).
"""
import base64
import hashlib
import hmac
import json
import re
import urllib.parse
from typing import Dict, List, Optional, Tuple

_LINK_RE = re.compile(r'<(?P<url>[^>]*)>\s*;\s*rel="(?P<rel>[^"]*)"')


class InvalidCursor(ValueError):
    pass


def parse_link_header(value: Optional[str]) -> Dict[str, str]:
    if not value:
        return {}
    return {m.group("rel"): m.group("url") for m in _LINK_RE.finditer(value)}


def next_url(response) -> Optional[str]:
    return parse_link_header(response.headers.get("link")).get("next")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode_cursor(secret: bytes, connector_id: str, url: str) -> str:
    payload = json.dumps({"c": connector_id, "u": url},
                         separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(secret, payload, hashlib.sha256).digest()
    return "%s.%s" % (_b64e(payload), _b64e(signature[:16]))


def decode_cursor(secret: bytes, connector_id: str, cursor: str, api_base: str) -> str:
    """Return the upstream URL, or raise. Four independent checks."""
    try:
        body, _, signature = cursor.partition(".")
        if not body or not signature:
            raise InvalidCursor("malformed cursor")
        payload = _b64d(body)
        expected = hmac.new(secret, payload, hashlib.sha256).digest()[:16]
        # compare_digest: a timing-safe comparison, because the alternative
        # leaks the signature one byte at a time to a patient caller.
        if not hmac.compare_digest(_b64d(signature), expected):
            raise InvalidCursor("cursor signature mismatch")
        data = json.loads(payload)
    except InvalidCursor:
        raise
    except Exception as exc:
        raise InvalidCursor("undecodable cursor") from exc

    if data.get("c") != connector_id:
        # A cursor minted for another connector is a cross-connector read.
        raise InvalidCursor("cursor belongs to a different connector")

    url = data.get("u") or ""
    if not _same_origin(url, api_base):
        # The signature proves WE minted it; this proves it still points where
        # it should even if a key ever leaked.
        raise InvalidCursor("cursor points outside the connector's API host")
    return url


def _same_origin(url: str, api_base: str) -> bool:
    try:
        a, b = urllib.parse.urlsplit(url), urllib.parse.urlsplit(api_base)
    except ValueError:
        return False
    return bool(a.scheme == b.scheme == "https" and a.netloc and a.netloc == b.netloc)
