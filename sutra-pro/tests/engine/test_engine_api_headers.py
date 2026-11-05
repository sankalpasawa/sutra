"""Security headers and the generated-content sandbox (work package E4, engine design 7.2, S3-web-14, D83): `text/html` replies
carry the sandbox CSP, every reply carries nosniff and no-referrer, none sets a cookie."""
import json
import os
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sutra_app.engine import views
from sutra_app.engine.api import mount
from sutra_app.engine.api.reply import SANDBOX_CSP, SECURITY_HEADERS, Reply, to_response
from sutra_app.engine.spec import EngineSettings

TOKEN = {"X-Sutra-Token": "fake-token-fake-token-0123"}
CSP = "sandbox allow-scripts allow-forms allow-popups; frame-ancestors 'self'"
PAGE = "<html><body><script>fetch('/api/state?dept=web')</script></body></html>"


@pytest.fixture
def api(fake_services):
    svc = fake_services
    ref = svc.add_run("web", status="waiting_user", files={
        "chat.jsonl": json.dumps({"meta": True, "run": "x", "output": "prd"}) + "\n", "summary.json": {"output_type": "prd"},
        "site/v1.html": PAGE, "site/shots/v1.png": b"\x89PNG-bytes", "prd.md": "# Title", "prd.docx": b"PK\x03\x04docx",
        "site/prd-v1.md": "# Title"})
    folder = svc.data_dir / ref.dir
    snap = views.idle_snapshot(EngineSettings(), views.MemoryPaths(str(folder / "l"), str(folder / "p")), ref.run_id)
    (folder / "snapshot.json").write_text(json.dumps({**snap, "status": "waiting", "saved": None}))
    (folder / "live.json").write_text(json.dumps({**views.EMPTY_LIVE, "pid": os.getpid(), "sites": 1, "output": "prd", "doc": False}))
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    mount(app, svc)
    return SimpleNamespace(svc=svc, ref=ref, client=TestClient(app, raise_server_exceptions=False))


def saved(api, path):
    return f"{path}{'&' if '?' in path else '?'}dept=web&run={api.ref.run_id}"


def live(path):
    return f"{path}{'&' if '?' in path else '?'}dept=web"


def test_sites_and_html_artifacts_carry_the_sandbox_csp(api):
    for url in (live("/site/latest"), live("/site/v1"), saved(api, "/site/latest"), saved(api, "/site/v1"),
                saved(api, "/api/artifact?name=site/v1.html")):
        got = api.client.get(url)
        assert got.status_code == 200 and got.text == PAGE, url
        assert got.headers["content-security-policy"] == CSP, url
        assert got.headers["content-type"] == "text/html; charset=utf-8"


def test_the_stub_pages_and_a_rendered_document_are_sandboxed_too(api):
    api.svc.add_run("sales", files={"chat.jsonl": "{}\n"})
    assert api.client.get(live("/site/latest").replace("web", "sales")).headers["content-security-policy"] == CSP      # "will appear" stub
    assert "No site" in api.client.get(saved(api, "/site/v9")).text
    assert api.client.get(saved(api, "/site/v9")).headers["content-security-policy"] == CSP


def test_other_replies_have_nosniff_and_no_referrer_and_no_csp(api):
    for url in (live("/api/state"), saved(api, "/shot/1"), saved(api, "/file/prd.md"), saved(api, "/api/artifact?name=prd.md"),
                saved(api, "/file/prd.docx"), live("/api/refs"), live("/api/runs")):
        got = api.client.get(url)
        assert got.status_code == 200, url
        for name, value in SECURITY_HEADERS.items():
            assert got.headers[name] == value, (url, name)
        assert "content-security-policy" not in got.headers, url


def test_errors_and_refusals_carry_the_headers_too(api):
    for got in (api.client.get("/api/state"), api.client.get("/api/state?dept=nope"), api.client.get(saved(api, "/shot/9")),
                api.client.post("/api/say?dept=web", json={}, headers=TOKEN),
                api.client.get("/api/engine/settings?dept=nope"), api.client.get("/api/state?dept=web&run=zzz")):
        assert got.status_code >= 400
        assert got.headers["x-content-type-options"] == "nosniff" and got.headers["referrer-policy"] == "no-referrer"


def test_no_response_sets_a_cookie(api):
    urls = [live(p) for p in ("/api/state", "/api/map", "/site/latest", "/api/engine/settings", "/api/refs")]
    urls += [saved(api, p) for p in ("/shot/1", "/file/prd.docx", "/api/artifact?name=site/v1.html")] + ["/api/state", "/api/state?dept=zz"]
    for url in urls:
        got = api.client.get(url, cookies={"sutra_dept": "web"})
        assert "set-cookie" not in got.headers, url
    for path in ("/api/say", "/api/reset", "/api/output"):
        assert "set-cookie" not in api.client.post(path + "?dept=web", json={"text": "x"}, headers=TOKEN).headers
    assert "set-cookie" not in api.client.put("/api/engine/settings", json={"set": {"budget": 5}}, headers=TOKEN).headers


def test_text_replies_are_utf8_and_not_cached_png_and_docx_are_raw(api):
    got = api.client.get(live("/api/state"))
    assert got.headers["content-type"] == "application/json; charset=utf-8" and got.headers["cache-control"] == "no-store"
    png = api.client.get(saved(api, "/shot/1"))
    assert (png.headers["content-type"], png.content, png.headers["cache-control"]) == ("image/png", b"\x89PNG-bytes", "no-store")
    docx = api.client.get(saved(api, "/file/prd.docx"))
    assert docx.content == b"PK\x03\x04docx" and docx.headers["content-type"] == views.DOCX
    assert docx.headers["content-disposition"] == 'attachment; filename="prd.docx"'


def test_the_docx_download_name_cannot_break_the_header():
    got = to_response(Reply(200, b"PK", views.DOCX, 'a"b\r\nSet-Cookie: x=1é.docx'), lambda t: t)
    assert "set-cookie" not in got.headers and got.headers["content-disposition"] == 'attachment; filename="a_b__Set-Cookie_ x_1_.docx"'
    assert to_response(Reply(200, b"PK", views.DOCX), lambda t: t).headers["content-disposition"] == 'attachment; filename="prd.docx"'


def test_to_response_decodes_bytes_of_a_text_type_and_keeps_the_reply_cache(api):
    got = to_response(Reply(200, "café".encode(), "text/html", cache="max-age=60"), str.upper)
    assert got.body == "CAFÉ".encode() and got.headers["cache-control"] == "max-age=60"
    assert got.headers["content-security-policy"] == SANDBOX_CSP == CSP
    plain = to_response(Reply(404, "not found", "text/plain"), str)
    assert "content-security-policy" not in plain.headers and plain.status_code == 404
