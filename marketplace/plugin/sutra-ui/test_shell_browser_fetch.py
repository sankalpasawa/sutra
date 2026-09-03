"""test_shell_browser_fetch.py -- the desktop shell's hidden-window fetch service.

Why it exists: the agent's crawler read a real customer site on 2026-09-03 and every
plain request, robots.txt and the sitemap included, answered 429 with a JavaScript bot
challenge. Only a browser passes such a challenge, and the pass does not carry over
to a plain client. This app is a browser, so main.js runs a loopback service that
fetches through a hidden window and hands the backend its address and a token.

Electron is not importable here, so the contract is pinned as text, the way
test_update_install_guard.py pins the install check.

Run: .venv/bin/python -m pytest -q test_shell_browser_fetch.py
"""
import os
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))


class ShellBrowserFetch(unittest.TestCase):

    def setUp(self):
        self.src = Path(HERE, "electron", "main.js").read_text(encoding="utf-8")

    def test_01_service_is_loopback_only_and_token_checked(self):
        self.assertIn("server.listen(0, HOST", self.src, "an ephemeral port on the loopback host, never 0.0.0.0")
        self.assertIn('req.headers["x-sutra-browser"] !== BROWSER_TOKEN', self.src)
        self.assertIn("crypto.randomBytes(24)", self.src, "the token is minted per launch")

    def test_02_only_http_urls_and_one_in_flight(self):
        self.assertIn('if (!/^https?:$/.test(u.protocol)) throw new Error("only http(s) urls")', self.src)
        self.assertIn("browserQueue = browserQueue.then(", self.src, "requests are serialised")

    def test_03_hidden_sandboxed_window_that_denies_popups(self):
        i = self.src.index("function browserWindowFor")
        block = self.src[i:i + 1400]
        self.assertIn("show: false", block)
        self.assertIn("sandbox: true", block)
        self.assertIn("nodeIntegration: false", block)
        self.assertIn('setWindowOpenHandler(() => ({ action: "deny" }))', block)

    def test_04_in_page_fetch_returns_raw_bodies(self):
        """Navigation renders XML through a viewer; fetch() hands back the bytes."""
        self.assertIn("const r = await fetch(u, {credentials: 'include', redirect: 'follow'});", self.src)
        self.assertIn("return {status: r.status, url: r.url, text: t, content_type:", self.src)

    def test_05_the_backend_is_handed_address_and_token_before_it_starts(self):
        i_svc = self.src.index("startBrowserFetchService();")
        i_backend = self.src.index("backend = startBackend();")
        self.assertLess(i_svc, i_backend, "the service must be listening before the backend is spawned")
        self.assertIn("SEO_AGENT_BROWSER_FETCH: browserFetchUrl, SEO_AGENT_BROWSER_TOKEN: BROWSER_TOKEN", self.src)

    def test_06_a_challenge_is_retried_in_page_not_reported_as_the_page(self):
        self.assertIn("if (last && !browserChallenged(last) && last.status) return last;", self.src)
        self.assertIn("x-vercel-mitigated", self.src)
        self.assertIn("cf-mitigated", self.src)

    def test_07_windows_are_capped_and_retired_when_idle(self):
        self.assertIn("BROWSER_MAX_WINDOWS = 3", self.src)
        self.assertIn("BROWSER_IDLE_MS = 10 * 60 * 1000", self.src)

    def test_08_the_python_client_speaks_the_same_contract(self):
        py = Path(HERE, "seo_agent", "tools", "_browser.py").read_text(encoding="utf-8")
        self.assertIn('"X-Sutra-Browser": token', py)
        self.assertIn('base + "/fetch"', py)
        self.assertIn("SEO_AGENT_BROWSER_FETCH", py)
        # the in-page fetch is the same code in both places
        self.assertIn("fetch(u, {credentials: 'include', redirect: 'follow'})", py)


if __name__ == "__main__":
    unittest.main(verbosity=2)
