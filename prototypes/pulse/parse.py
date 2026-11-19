"""Gmail Message resource -> Pulse mail row (spec "Mail row"). Same code for mock and live."""
import base64
import re
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses
from html.parser import HTMLParser

BODY_MAX = 20_000
_BLOCK_TAGS = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "hr"}
_NEEDS_QUOTES = re.compile(r'[,;:<>"@()\[\]\\]')


def decode_header_value(raw: str) -> str:
    """Decode RFC 2047 encoded words to Unicode; undecodable input is returned as given."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def split_addresses(raw: str) -> list:
    """Split on top-level commas (quoted display names may contain commas) and decode each display name."""
    if not raw:
        return []
    out = []
    for name, addr in getaddresses([raw]):
        if not addr and not name:
            continue
        name = decode_header_value(name).strip()
        if name and _NEEDS_QUOTES.search(name):
            name = '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'
        out.append(f"{name} <{addr}>" if name else addr)
    return out


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    p.close()
    text = "".join(p.parts).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _iso_utc(internal_date) -> str:
    try:
        ms = int(internal_date)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _walk(part):
    yield part
    for sub in part.get("parts") or []:
        yield from _walk(sub)


def _charset(part) -> str:
    for h in part.get("headers") or []:
        if h.get("name", "").lower() == "content-type":
            m = Message()
            m["Content-Type"] = h.get("value", "")
            return m.get_content_charset() or "utf-8"
    return "utf-8"


def _decode_body(part) -> str:
    data = (part.get("body") or {}).get("data")
    if not data:
        return ""
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    try:
        return raw.decode(_charset(part), errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _body_text(payload) -> str:
    parts = [p for p in _walk(payload) if not p.get("filename")]
    for p in parts:
        if p.get("mimeType", "").lower() == "text/plain" and (p.get("body") or {}).get("data"):
            return _decode_body(p)
    for p in parts:
        if p.get("mimeType", "").lower() == "text/html" and (p.get("body") or {}).get("data"):
            return html_to_text(_decode_body(p))
    return ""


def to_row(msg: dict, full: bool) -> dict:
    payload = msg.get("payload") or {}
    headers = {}
    for h in payload.get("headers") or []:
        headers.setdefault(h.get("name", "").lower(), h.get("value", ""))
    row = {
        "id": msg.get("id", ""),
        "thread_id": msg.get("threadId", ""),
        "from": decode_header_value(headers.get("from", "")),
        "to": split_addresses(headers.get("to", "")),
        "cc": split_addresses(headers.get("cc", "")),
        "date": _iso_utc(msg.get("internalDate")),
        "subject": decode_header_value(headers.get("subject", "")),
        "snippet": msg.get("snippet", ""),
        "labels": list(msg.get("labelIds") or []),
        "attachments": [{"name": p["filename"], "mime": p.get("mimeType", ""),
                         "size": int((p.get("body") or {}).get("size", 0))}
                        for p in _walk(payload) if p.get("filename")],
    }
    if full:
        text = _body_text(payload)
        row["body_text"] = text[:BODY_MAX]
        row["body_truncated"] = len(text) > BODY_MAX
    return row
