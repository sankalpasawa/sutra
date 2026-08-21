"""Loopback redirect capture.

Used by providers that offer no device flow. Slack is the first; Google will be
the second, with PKCE added.

WHAT PROTECTS THIS FLOW, AND WHAT DOES NOT

GitHub's device flow has no redirect at all, so there is nothing to intercept.
Here a browser delivers an authorization code to a port on this machine, and
any process running as this user can try to take it. Slack offers no PKCE, so
`state` is the ONLY thing binding the returned code to our request.

Everything below is therefore defence around a weakness we cannot remove:

  bind before the browser opens   A squatter must beat us to the port BEFORE we
                                  start, not after. If the bind fails we abort
                                  rather than fall back to another port -- a
                                  fallback port would not match the registered
                                  redirect URI anyway, and silently trying
                                  others is how you end up handing the code to
                                  whoever is listening.
  one request, then close         The listener answers exactly one callback and
                                  shuts down. It is not a server; it is a
                                  catcher with a lifetime of seconds.
  127.0.0.1 only                  Never 0.0.0.0. The loopback interface is not
                                  reachable from the network.
  Host header checked             Blocks DNS rebinding, where a hostile page
                                  resolves a name it controls to 127.0.0.1.
  state verified before use       256-bit, single-use, operator-bound, hashed
                                  at rest -- the same discipline as GitHub's.
  hard timeout                    An abandoned flow does not leave a listener
                                  running for the life of the app.

Residual risk is real and is recorded as T-21 in design/06-security.md rather
than argued away.
"""
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Optional

BIND_HOST = "127.0.0.1"
ALLOWED_HOSTS = ("localhost", "127.0.0.1")

_PAGE = """<!doctype html><meta charset="utf-8">
<title>Sutra</title>
<style>body{font:15px/1.6 -apple-system,system-ui,sans-serif;background:#0C0B09;
color:#F5F0E8;display:grid;place-items:center;height:100vh;margin:0}
div{text-align:center;max-width:26rem}p{color:#8C857D;font-size:13px}</style>
<div><h2>%s</h2><p>%s</p></div>"""


class LoopbackError(RuntimeError):
    pass


class _Handler(BaseHTTPRequestHandler):
    server_version = "Sutra"
    sys_version = ""

    def log_message(self, *args):
        """Silence. The default handler prints every request to stderr, and the
        query string of THIS request contains an authorization code."""

    def do_GET(self):
        captured = self.server.captured
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ALLOWED_HOSTS:
            # DNS rebinding: a page on a hostile domain that resolves to
            # 127.0.0.1 would otherwise reach this listener.
            #
            # Rejected WITHOUT completing the flow. An earlier version returned
            # here without setting `done` while the listener served exactly one
            # request -- so a single hostile probe consumed the listener and the
            # user's real callback could never arrive. Now the catcher keeps
            # waiting, and a probe costs the attacker a 400.
            self.server.rejected.append("bad_host")
            self._respond(400, "Rejected", "Unexpected Host header.")
            return

        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != self.server.expected_path:
            # Same reasoning: a stray request to another path must not consume
            # the one callback we are waiting for.
            self.server.rejected.append("bad_path")
            self._respond(404, "Not found", "")
            return

        params = urllib.parse.parse_qs(parsed.query)
        code = (params.get("code") or [None])[0]
        state = (params.get("state") or [None])[0]
        error = (params.get("error") or [None])[0]

        if error:
            captured["error"] = error
            self._respond(200, "Authorization declined",
                          "You can close this window and return to Sutra.")
        elif not code or not state:
            captured["error"] = "missing_parameters"
            self._respond(400, "Incomplete callback",
                          "The provider did not return a code.")
        else:
            captured["code"] = code
            captured["state"] = state
            self._respond(200, "Connected",
                          "You can close this window and return to Sutra.")
        self.server.done.set()

    def _respond(self, status, heading, detail):
        body = (_PAGE % (heading, detail)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # This page's URL contains an authorization code. Keep it out of any
        # cache and out of the referrer sent to whatever the user clicks next.
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)


class LoopbackCatcher:
    """Binds the port, catches one callback, shuts down.

    Bind happens in __init__ -- BEFORE the caller opens a browser -- so that a
    port already taken is an error we raise instead of a code we hand to
    whoever holds it.
    """

    def __init__(self, port: int, path: str, timeout: int = 300):
        self.port = port
        self.path = path
        self.timeout = timeout
        try:
            self._server = HTTPServer((BIND_HOST, port), _Handler)
        except OSError as exc:
            raise LoopbackError(
                "cannot bind %s:%d (%s). Another process is using the port that "
                "the registered redirect URI names; Sutra will not fall back to "
                "a different port, because the provider would reject it and "
                "because trying ports blindly is how a code reaches the wrong "
                "listener." % (BIND_HOST, port, exc))
        # HTTPServer sets allow_reuse_address (SO_REUSEADDR) by default, and
        # that is correct: it permits rebinding a port whose previous
        # CONNECTION is still in TIME_WAIT, which is what happens the moment a
        # user disconnects and reconnects. It does NOT let a second process
        # bind the same live port -- that is SO_REUSEPORT, which is never set
        # here and is the option that would actually help a squatter.
        self._server.captured: Dict[str, str] = {}
        self._server.done = threading.Event()
        self._server.rejected = []
        self._server.expected_path = path
        # Poll rather than block forever, so the loop can notice `done` and
        # `_closing` between requests.
        self._server.timeout = 0.5
        self._closing = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self):
        """Serve until a VALID callback arrives, we are closed, or we time out.

        Not handle_request() once: a rejected probe would consume the single
        request and strand the user's real callback.
        """
        deadline = time.monotonic() + self.timeout
        while not self._server.done.is_set() and not self._closing.is_set():
            if time.monotonic() > deadline:
                return
            try:
                self._server.handle_request()
            except OSError:
                return

    def start(self):
        self._thread.start()
        return self

    def wait(self) -> Dict[str, str]:
        """Block for one callback. Returns {code, state} or {error}."""
        if not self._server.done.wait(self.timeout):
            self.close()
            raise LoopbackError("timed out waiting for the authorization callback")
        self.close()
        return dict(self._server.captured)

    def close(self):
        self._closing.set()
        try:
            self._server.server_close()
        except Exception:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.close()


def port_is_free(port: int) -> bool:
    """Pre-flight so the UI can say 'port busy' before opening a browser.

    The probe must set SO_REUSEADDR because the real listener does (HTTPServer
    sets it by default). Without it the probe reports "busy" for a port whose
    previous connection is merely in TIME_WAIT -- which is the state left
    immediately after a successful connect, so a user who disconnected and
    reconnected would be told the port was taken when it was not.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind((BIND_HOST, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()
