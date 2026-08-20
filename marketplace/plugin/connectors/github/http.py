"""HTTP transport, stdlib only.

urllib.request rather than httpx: sutra-ui runs on three dependencies and its
test suite refuses to import a fourth. The cost is that calls are blocking and
must run in a threadpool executor when called from FastAPI -- a real cost,
accepted deliberately (founder decision 2026-08-20).

Transport is an interface so tests never touch the network. A test that needs a
live GitHub is an integration test and is marked as one.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple


class HttpResponse:
    __slots__ = ("status", "headers", "body")

    def __init__(self, status: int, headers: Dict[str, str], body: bytes):
        self.status = status
        # Header names are case-insensitive; normalising once avoids a class of
        # bug where `Retry-After` is present and `retry-after` is looked up.
        self.headers = {str(k).lower(): v for k, v in (headers or {}).items()}
        self.body = body or b""

    def json(self):
        if not self.body:
            return {}
        try:
            return json.loads(self.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def header_int(self, name, default=None):
        try:
            return int(self.headers[name])
        except (KeyError, TypeError, ValueError):
            return default


class Transport:
    def request(self, method, url, headers=None, body=None, timeout=30) -> HttpResponse:
        raise NotImplementedError


class UrllibTransport(Transport):
    def request(self, method, url, headers=None, body=None, timeout=30) -> HttpResponse:
        request = urllib.request.Request(
            url, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(response.status, dict(response.headers),
                                    response.read())
        except urllib.error.HTTPError as exc:
            # A 4xx/5xx is a response, not an exception: the body and headers
            # carry the rate-limit and SSO signals we classify on.
            return HttpResponse(exc.code, dict(exc.headers or {}), exc.read())
        except urllib.error.URLError as exc:
            raise ConnectionError(str(exc.reason)) from exc


class FakeTransport(Transport):
    """Scripted transport for tests. Records what was sent so a test can assert
    that a client_secret was never transmitted."""

    def __init__(self, responses=None):
        self.responses: List[HttpResponse] = list(responses or [])
        self.calls: List[Tuple[str, str, Dict, Optional[bytes]]] = []

    def push(self, status=200, payload=None, headers=None, raw=None):
        body = raw if raw is not None else json.dumps(payload or {}).encode("utf-8")
        self.responses.append(HttpResponse(status, headers or {}, body))
        return self

    def request(self, method, url, headers=None, body=None, timeout=30):
        self.calls.append((method, url, dict(headers or {}), body))
        if not self.responses:
            raise AssertionError("FakeTransport exhausted on %s %s" % (method, url))
        return self.responses.pop(0)

    # -- assertions used by the security tests ---------------------------
    def sent_bodies(self) -> List[str]:
        return [(b or b"").decode("utf-8") for _, _, _, b in self.calls]

    def transmitted(self, needle: str) -> bool:
        if any(needle in body for body in self.sent_bodies()):
            return True
        return any(needle in str(h) for _, _, h, _ in self.calls)
