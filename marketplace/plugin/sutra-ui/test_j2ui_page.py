"""test_j2ui_page.py -- the route that serves the J2 prototype's page (UI-port package j2ui-shell, E3).

Named claims, on the full app (TestClient, loopback host) with a seeded website department:
  - GET /j2ui/{ref}/ is 200 for a department of the engine runtime whose kind is website, with the page's content
    security policy (own origin, inline script and style, frame-ancestors 'self'; the two Google hosts only while the
    fonts are not vendored), nosniff and no-store; the body is the copy, begins <!doctype html>, holds the j2host.js line
    once and no root-absolute api, site, file or shot path
  - /j2ui/{ref} redirects to the slash
  - a Root, a department of kind default or organic, a department of the first build, an unknown ref and a ref that
    is a path are 404 {"error": "no such department"} on the page, on j2host.js and on fonts/
  - the origin guard still applies under /j2ui: a POST that carries an Origin and no panel token is 403, and with the
    token it passes the guard
  - a built site answered under /j2ui/{ref}/site/ carries the SAFE headers (the department's own files are shown, never run)
  - fonts/ serves only the names the pin lists, with the right type and an hour of cache; j2host.js and the page are read
    again only when the file changes; a read of any of it writes nothing

Run: ./run-tests.sh test_j2ui_page.py"""
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app as app_module
import j2ui_page

UI = Path(__file__).resolve().parent
ASSETS = UI / "j2ui_assets"
WEB, ROOT, DEFAULT, ORGANIC, OLD = "dref-web", "dref-root", "dref-default", "dref-organic", "dref-old"
GUARD = re.compile(rb'(["\'`])/(api|site|file|shot)/')


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    monkeypatch.setenv("SUTRA_NATIVE_HOME", str(tmp_path / "registry"))
    monkeypatch.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    import website_dept as W
    W.create(WEB, "City Care Hospital Website", "A website for the hospital", kind="website")
    W.create(ROOT, "Root", "Makes departments", kind="root")
    W.create(DEFAULT, "Billing", "Billing", kind="default")
    W.create(ORGANIC, "Notes", "Notes", kind="organic")
    monkeypatch.setenv("SUTRA_ENGINE_RUNTIME", "1")
    W.create(OLD, "The first build", "The first build's way", kind="website")
    monkeypatch.delenv("SUTRA_ENGINE_RUNTIME")
    monkeypatch.setattr(j2ui_page, "_CACHE", {})
    return W


@pytest.fixture
def client(env):
    return TestClient(app_module.app, base_url="http://127.0.0.1")


def test_the_page_is_served_with_its_policy_and_is_the_copy(client):
    r = client.get("/j2ui/%s/" % WEB)
    assert r.status_code == 200
    assert r.headers["content-type"] == "text/html; charset=utf-8"
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
    assert r.content == (ASSETS / "j2_ui.html").read_bytes()
    assert r.content.startswith(b"<!doctype html>")
    assert r.content.count(b'<script src="j2host.js"></script>') == 1
    assert not GUARD.search(r.content), "every path in the page is relative"
    csp = r.headers["content-security-policy"]
    pinned = json.loads((ASSETS / "PINNED.json").read_text())
    assert "frame-ancestors 'self'" in csp and "default-src 'self'" in csp and "connect-src 'self'" in csp
    assert "script-src 'self' 'unsafe-inline'" in csp and "object-src 'none'" in csp and "base-uri 'none'" in csp
    assert "form-action 'none'" in csp and "frame-src 'self'" in csp and "img-src 'self' data:" in csp
    if pinned["local_fonts"]:
        assert "googleapis" not in csp and "gstatic" not in csp and "font-src 'self';" in csp
    else:
        assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com" in csp and "font-src https://fonts.gstatic.com" in csp
    assert client.get("/j2ui/%s/index.html" % WEB).content == r.content


def test_the_policy_names_no_google_host_once_the_fonts_are_vendored():
    on, off = j2ui_page.csp(True), j2ui_page.csp(False)
    assert "google" not in on and "gstatic" not in on
    assert "font-src 'self'; " in on and "style-src 'self' 'unsafe-inline'; " in on
    assert "https://fonts.googleapis.com" in off and "font-src https://fonts.gstatic.com" in off
    assert on.endswith("frame-ancestors 'self'") and off.endswith("frame-ancestors 'self'")


def test_the_page_follows_the_pin_for_its_policy(client, monkeypatch):
    monkeypatch.setattr(j2ui_page, "pin", lambda: {"local_fonts": True})
    assert "gstatic" not in client.get("/j2ui/%s/" % WEB).headers["content-security-policy"]


def test_a_request_without_the_slash_is_redirected_to_it(client):
    r = client.get("/j2ui/%s" % WEB, follow_redirects=False)
    assert r.status_code in (301, 307, 308) and r.headers["location"].endswith("/j2ui/%s/" % WEB)
    assert client.get("/j2ui/%s" % WEB).status_code == 200


@pytest.mark.parametrize("ref, why", [(OLD, "the first build's way"), ("dref-nobody", "an unknown ref"), (".hidden", "a dot ref")])
def test_only_a_department_on_the_engine_runtime_has_the_page(client, ref, why):
    for tail in ("", "index.html", "j2host.js", "fonts/fonts.css"):
        r = client.get("/j2ui/%s/%s" % (ref, tail))
        assert r.status_code == 404 and r.json() == {"error": "no such department"}, why + " / " + tail


@pytest.mark.parametrize("ref", [WEB, ROOT, DEFAULT, ORGANIC])
def test_every_kind_on_the_engine_runtime_has_the_page_and_scoped_agrees_with_need(client, ref):
    import j2ui_common
    for tail in ("", "index.html", "j2host.js"):
        assert client.get("/j2ui/%s/%s" % (ref, tail)).status_code == 200, tail
    assert j2ui_page._scoped(ref) is True and j2ui_common.need(ref)["ref"] == ref
    assert j2ui_page._scoped(OLD) is False


def test_the_scope_is_the_adapters_when_the_adapter_is_in_the_tree(client, monkeypatch):
    class NotJ2(Exception):
        pass

    class Common:
        pass
    seen = []

    def need(ref):
        seen.append(ref)
        if ref != WEB:
            raise NotJ2(ref)
    Common.need, Common.NotJ2 = staticmethod(need), NotJ2
    monkeypatch.setattr(j2ui_page, "_common", Common)
    assert client.get("/j2ui/%s/" % WEB).status_code == 200
    assert client.get("/j2ui/%s/" % DEFAULT).status_code == 404
    assert seen == [WEB, DEFAULT], "j2ui_common.need decided, the record was not read here"


def test_the_origin_guard_still_applies_under_j2ui(client):
    here = {"Origin": "http://127.0.0.1:8330"}
    url = "/j2ui/%s/api/say" % WEB
    r = client.post(url, json={"text": "hello"}, headers=here)
    assert r.status_code == 403, "a write that carries an Origin and no token is refused"
    token = client.get("/api/panel-token").json()["token"]
    r = client.post(url, json={"text": "hello"}, headers=dict(here, **{"X-Sutra-Panel": token}))
    assert r.status_code != 403, "with the panel token it passes the guard"
    try:
        import j2ui_api  # noqa: F401
    except ModuleNotFoundError:
        assert r.status_code in (404, 405), "the adapter is not in the tree yet: nothing answers the call"
    else:
        assert r.status_code in (200, 400, 409), r.text
    cross = client.post(url, json={"text": "x"}, headers={"Origin": "http://evil.example", "X-Sutra-Panel": token})
    assert cross.status_code == 403, "a cross-origin write is refused whatever it carries"


def test_a_built_site_under_j2ui_carries_the_safe_headers(client, env):
    pytest.importorskip("j2ui_api", reason="the adapter (j2ui-core) is not in the tree yet; this reruns after it merges")
    import website_api
    env.add_version(WEB, "Build", {"index.html": "<h1>Hello</h1><script>alert(1)</script>", "style.css": "h1{color:red}"},
                    ["Site plan v1"], "r-1", {"ok": True, "notes": []})
    for tail in ("site/latest/index.html", "site/v1/index.html", "site/latest", "file/x.md", "shot/1"):
        r = client.get("/j2ui/%s/%s" % (WEB, tail), follow_redirects=True)
        for k, v in website_api.SAFE.items():
            assert r.headers.get(k.lower()) == v, "%s lacks %s" % (tail, k)


# ── j2host.js and fonts/ ──────────────────────────────────────────────────────────────────────────────────────────
def test_j2host_is_served_as_javascript_and_never_cached(client):
    r = client.get("/j2ui/%s/j2host.js" % WEB)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/javascript")
    assert r.headers["cache-control"] == "no-store" and r.content == (ASSETS / "j2host.js").read_bytes()


@pytest.fixture
def fonts(tmp_path, monkeypatch, env):
    """A small vendored set in a folder of its own, listed in a pin of its own."""
    root = tmp_path / "assets"
    (root / "fonts").mkdir(parents=True)
    (root / "fonts" / "fonts.css").write_text("@font-face{src:url(a.woff2)}")
    (root / "fonts" / "a.woff2").write_bytes(b"wOF2 a")
    (root / "fonts" / "LICENSE.txt").write_text("SIL OFL")
    (root / "fonts" / "stray.woff2").write_bytes(b"wOF2 not in the pin")
    (root / "fonts" / "notes.html").write_text("<p>x</p>")
    (root / "j2_ui.html").write_bytes(b"<!doctype html>one")
    (root / "j2host.js").write_text("/* host */")
    names = ["fonts.css", "a.woff2", "LICENSE.txt", "notes.html", "gone.woff2"]
    pin = {"local_fonts": True, "app": {"files": {"j2ui_assets/fonts/" + n: {} for n in names}}}
    monkeypatch.setattr(j2ui_page, "ASSETS", root)
    monkeypatch.setattr(j2ui_page, "pin", lambda: pin)
    return root


def test_fonts_serves_only_the_names_the_pin_lists_with_the_right_type(client, fonts):
    css = client.get("/j2ui/%s/fonts/fonts.css" % WEB)
    assert css.status_code == 200 and css.headers["content-type"] == "text/css; charset=utf-8" and "a.woff2" in css.text
    w = client.get("/j2ui/%s/fonts/a.woff2" % WEB)
    assert w.status_code == 200 and w.headers["content-type"] == "font/woff2" and w.content == b"wOF2 a"
    assert w.headers["cache-control"] == "public, max-age=3600" and w.headers["x-content-type-options"] == "nosniff"
    assert client.get("/j2ui/%s/fonts/LICENSE.txt" % WEB).headers["content-type"].startswith("text/plain")
    for name in ("stray.woff2", "gone.woff2", "notes.html", "..%2Fj2_ui.html", "%2e%2e%2fj2_ui.html", "nothing.woff2"):
        r = client.get("/j2ui/%s/fonts/%s" % (WEB, name))
        assert r.status_code == 404, name


def test_fonts_for_a_department_that_has_no_page_is_404(client, fonts):
    assert client.get("/j2ui/%s/fonts/a.woff2" % OLD).status_code == 404


def test_a_file_is_read_again_only_when_it_changed(client, fonts):
    first = client.get("/j2ui/%s/" % WEB)
    assert first.content == b"<!doctype html>one"
    held = j2ui_page._CACHE[fonts / "j2_ui.html"][2]
    client.get("/j2ui/%s/" % WEB)
    assert j2ui_page._CACHE[fonts / "j2_ui.html"][2] is held, "an unchanged file is not read again"
    (fonts / "j2_ui.html").write_bytes(b"<!doctype html>two, longer")
    assert client.get("/j2ui/%s/" % WEB).content == b"<!doctype html>two, longer"


def test_a_missing_file_is_a_plain_404_and_not_a_stack_trace(client, fonts):
    (fonts / "j2_ui.html").unlink()
    (fonts / "j2host.js").unlink()
    for tail in ("", "j2host.js"):
        r = client.get("/j2ui/%s/%s" % (WEB, tail))
        assert r.status_code == 404 and r.text == "not found"


def test_a_read_of_the_page_its_script_and_its_fonts_writes_nothing(client, fonts, tmp_path):
    def snapshot():
        return sorted((str(p.relative_to(tmp_path)), p.stat().st_mtime_ns, p.stat().st_size) for p in tmp_path.rglob("*") if p.is_file())
    before = snapshot()
    for tail in ("", "j2host.js", "fonts/fonts.css", "fonts/a.woff2", "fonts/nothing.woff2"):
        client.get("/j2ui/%s/%s" % (WEB, tail))
    client.get("/j2ui/%s/" % ROOT)
    assert snapshot() == before
