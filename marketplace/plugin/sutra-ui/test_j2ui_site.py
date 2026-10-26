"""test_j2ui_site.py -- the J2 page's Preview tab, site/file/shot (j2ui_site.py; UIPORT j2ui-views M2).

Named claims:
  M2a  site/latest, site/vN and site/N answer 302 with a relative Location <key>/index.html; the redirected request
       returns the page with its css inlined; an unknown vN is 404; nothing built yet is the placeholder paragraph, verbatim,
       with status 200
  M2b  links stay inside their version: a relative about.html link in v1 resolves, by plain URL joining, to site/v1/about.html
       and serves v1's file even after v2 exists; other files are served raw with their type
  M2c  traversal (../x, %2e%2e/x, /etc/passwd, a backslash, a NUL), an unlisted file and a missing version are 404
  M2d  every tuple carries the SAFE headers (sandbox, script-src 'none', nosniff, no-store); file() and shot() are 404 for
       every input; nothing here writes or raises
Shares the department fixtures and the Ctx stand-in of test_j2ui_artifacts.py.
"""
from urllib.parse import urljoin, urlsplit

import pytest

from test_j2ui_artifacts import (REF, ABOUT_HTML, SITE_HTML, add_ver, make_ctx, mods, seed_line)  # noqa: F401 -- mods is a fixture

BASE = "http://127.0.0.1:8000/j2ui/%s/" % REF


def get(ctx, url, hops=3):
    """A request for BASE + url as the router makes it: site/<key> and site/<key>/<path> go to j2ui_site.site, a 302 is
    followed with a relative Location; returns (status, body, mime, headers) of the last answer."""
    import j2ui_site as S
    for _ in range(hops):
        rel = urlsplit(url).path[len(urlsplit(BASE).path):]
        parts = rel.split("/", 2)
        assert parts[0] == "site", rel
        out = S.site(ctx, parts[1], parts[2] if len(parts) > 2 else "")
        if out[0] != 302:
            return out
        url = urljoin(url, out[3]["Location"])
    raise AssertionError("too many redirects")


def test_m2a_latest_v_and_n_redirect_to_the_index_of_their_version(ctx2):
    import j2ui_site as S
    for key in ("latest", "v1", "1", "v2", "2"):
        status, body, mime, headers = S.site(ctx2, key)
        assert status == 302 and body == b"" and headers["Location"] == "%s/index.html" % key, key
        assert "/" not in headers["Location"].split("/index.html")[0]            # relative, so the links inside stay inside


def test_m2a_the_redirected_request_returns_the_page_with_its_css_inlined(ctx2):
    for key, v in (("latest", 2), ("v1", 1), ("1", 1)):
        status, body, mime, headers = get(ctx2, BASE + "site/" + key)
        text = body.decode("utf-8")
        assert status == 200 and mime == "text/html"
        assert "<style>body{color:#123}</style>" in text and "<link" not in text
        assert "City Care v%d" % v in text, key


def test_m2a_an_unknown_version_is_404(ctx2):
    import j2ui_site as S
    for key in ("v99", "99", "v0", "0", "garbage", "", "V1", "v1.5", "latest2", "../x", "v-1"):
        status, body, mime, headers = S.site(ctx2, key)
        assert (status, body, mime) == (404, b"not found", "text/plain"), key


def test_m2a_nothing_built_yet_is_the_placeholder_verbatim(mods):
    import j2ui_site as S
    ctx = make_ctx(mods)
    want = "<p style='font:15px system-ui;color:#667;padding:24px'>Your website will appear here once it's built.</p>"
    for key in ("latest", "v1", "1"):
        status, body, mime, headers = S.site(ctx, key)
        assert (status, body.decode("utf-8"), mime) == (200, want, "text/html"), key
    assert S.NOT_YET == want
    assert S.site(ctx, "garbage")[0] == 404
    assert S.site(ctx, "latest", "index.html")[0] == 404                         # no version, so no file of one


def test_m2a_the_placeholder_follows_the_previewable_artifact_not_the_live_site(mods):
    import j2ui_site as S
    seed_line(mods[0], upto=3)                                                   # Brief, Site plan, Pages: no Build yet
    assert S.site(make_ctx(mods), "latest")[0] == 200
    add_ver(mods[0], "Live site")                                                # a Live site alone is not the Preview's artifact
    assert S.site(make_ctx(mods), "latest")[1].decode("utf-8") == S.NOT_YET


def test_m2b_a_relative_link_stays_inside_its_version(mods):
    import j2ui_site as S
    W = mods[0]
    seed_line(W, upto=4)
    add_ver(W, "Build", {"index.html": SITE_HTML.replace("City Care", "NEW"), "style.css": "body{color:#999}",
                         "about.html": "<html><body>about of version two</body></html>"})
    ctx = make_ctx(mods)
    status, page, _, _ = get(ctx, BASE + "site/v1")
    assert status == 200 and b"about.html" in page
    # the page's link, joined onto the URL the redirect left the frame at, is version 1's page
    landed = urljoin(BASE + "site/v1", S.site(ctx, "v1")[3]["Location"])
    assert landed == BASE + "site/v1/index.html"
    link = urljoin(landed, "about.html")
    assert link == BASE + "site/v1/about.html"
    status, body, mime, _ = get(ctx, link)
    assert (status, mime) == (200, "text/html") and body.decode("utf-8") == ABOUT_HTML       # v1's file, raw, though v2 exists
    status, body, _, _ = get(ctx, BASE + "site/v2/about.html")
    assert b"about of version two" in body
    assert b"about of version two" in get(ctx, BASE + "site/latest/about.html")[1]


def test_m2b_other_files_are_served_raw_with_their_type(ctx2):
    import j2ui_site as S
    status, body, mime, _ = S.site(ctx2, "v1", "style.css")
    assert (status, body, mime) == (200, b"body{color:#123}", "text/css")
    status, body, mime, _ = S.site(ctx2, "v1", "about.html")
    assert (status, mime) == (200, "text/html") and b'<link href="style.css" rel="stylesheet">' in body      # raw: not inlined
    status, body, mime, _ = S.site(ctx2, "v1", "index.html")
    assert b"<link" not in body                                                  # only index.html is inlined
    assert S._mime("a.json") == "text/plain" and S._mime("a.htm") == "text/html" and S._mime("noext") == "text/plain"


def test_m2b_a_stored_script_comes_back_unchanged_under_the_safe_headers(mods):
    import j2ui_site as S
    page = "<html><body><script>alert(1)</script></body></html>"
    add_ver(mods[0], "Build", {"index.html": page, "style.css": ""})
    status, body, mime, headers = S.site(make_ctx(mods), "latest", "index.html")
    assert body.decode("utf-8") == page and "script-src 'none'" in headers["Content-Security-Policy"]


@pytest.mark.parametrize("path", ["../x", "%2e%2e/x", "/etc/passwd", "..", "../../dept.json", "a/../../dept.json", "style.css/..",
                                  "about.html\\x", "back\\slash.html", "nul\x00.html", "nope.html", "dept.json", "./index.html",
                                  "index.html/", "//index.html", "STYLE.CSS"])
def test_m2c_traversal_and_unlisted_files_are_404(ctx2, path):
    import j2ui_site as S
    status, body, mime, headers = S.site(ctx2, "v1", path)
    assert (status, body, mime) == (404, b"not found", "text/plain")


def test_m2c_a_missing_version_with_a_path_is_404(ctx2):
    import j2ui_site as S
    for key in ("v99", "0", "x", "../v1"):
        assert S.site(ctx2, key, "index.html")[0] == 404


def test_m2d_every_tuple_carries_the_safe_headers(ctx2, mods):
    import j2ui_site as S
    import website_api
    assert S.SAFE_HEADERS == dict(website_api.SAFE)
    assert "sandbox" in S.SAFE_HEADERS["Content-Security-Policy"] and "script-src 'none'" in S.SAFE_HEADERS["Content-Security-Policy"]
    outs = [S.site(ctx2, "latest"), S.site(ctx2, "v1", "index.html"), S.site(ctx2, "v1", "style.css"), S.site(ctx2, "v99"),
            S.site(ctx2, "v1", "../x"), S.site(make_ctx(mods), "latest"), S.file(ctx2, "prd.md"), S.shot(ctx2, 1)]
    for status, body, mime, headers in outs:
        for k, v in S.SAFE_HEADERS.items():
            assert headers[k] == v, (status, k)
        assert isinstance(body, bytes) and isinstance(mime, str) and isinstance(status, int)
    headers = S.site(ctx2, "v1")[3]
    assert headers["X-Content-Type-Options"] == "nosniff" and headers["Cache-Control"] == "no-store"
    headers.update({"x": "y"})
    assert "x" not in S.SAFE_HEADERS                                              # a copy per answer


def test_m2d_file_and_shot_are_404_for_every_input(ctx2):
    import j2ui_site as S
    for name in ("prd.md", "prd.docx", "../x", "", None, 7, "build/v1/index.html"):
        assert S.file(ctx2, name)[:3] == (404, b"not found", "text/plain")
    for n in (0, 1, 8, "8", "x", None, -1, "../x"):
        assert S.shot(ctx2, n)[:3] == (404, b"not found", "text/plain")


def test_m2d_nothing_here_writes_or_raises(ctx2, mods):
    import j2ui_site as S
    W = mods[0]
    before = sorted((str(p.relative_to(W.ddir(REF))), p.stat().st_mtime_ns) for p in W.ddir(REF).rglob("*") if p.is_file())
    for key, path in (("latest", ""), ("v1", "index.html"), ("v2", "about.html"), ("zz", "q"), (None, None), (7, 7)):
        S.site(ctx2, key, path)
    assert S.site(object(), "latest", "index.html")[0] == 404                      # not a ctx at all
    after = sorted((str(p.relative_to(W.ddir(REF))), p.stat().st_mtime_ns) for p in W.ddir(REF).rglob("*") if p.is_file())
    assert before == after


@pytest.fixture
def ctx2(mods):
    """A department whose Build has two versions."""
    W = mods[0]
    seed_line(W, upto=4)
    add_ver(W, "Build")
    return make_ctx(mods)
