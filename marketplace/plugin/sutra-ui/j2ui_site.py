"""j2ui_site.py -- the J2 page's Preview tab: /site/{key}[/{path}], /file/{name} and /shot/{n} for a website department.

The page shows the built site in a frame at site/latest or site/vN. A site is many files that link to each other, and the
prototype held each version as one page; here a version is a folder, so a request for site/<key> is answered with a
redirect to site/<key>/index.html, and every relative link inside the page (about.html, style.css) then stays inside
that version: site/v3/about.html is version 3's page, never the latest version's. Reads only; no model call.

  site(ctx, key, path='')  (status, body, mime, headers) for the previewable artifact (j2ui_artifacts.previewable)
  file(ctx, name)          always 404: a website team has no .md or .docx download
  shot(ctx, n)             always 404: a website team records no screenshots (the page then says what it says)

What the department's model or engines wrote is shown, never run: every tuple carries SAFE_HEADERS (website_api.SAFE:
sandbox, no script, no object, no base, no form), so a built page cannot read the panel it is previewed in. The router
(j2ui_api) adds the same headers; they are set here as well so this module alone is safe to test and to call.
"""
import posixpath
import re

import website_dept as W
import website_api
from j2ui_artifacts import inline_css, previewable

SAFE_HEADERS = dict(website_api.SAFE)
NOT_YET = "<p style='font:15px system-ui;color:#667;padding:24px'>Your website will appear here once it's built.</p>"
_KEY = re.compile(r"v?(\d+)")


def _out(status, body, mime, **more):
    if isinstance(body, str):
        body = body.encode("utf-8")
    return status, body, mime, dict(SAFE_HEADERS, **more)


def _gone():
    return _out(404, b"not found", "text/plain")


def _versions(ctx):
    """(artifact name, [version numbers]) of the artifact the Preview tab shows."""
    name = previewable(ctx)
    for a in getattr(ctx, "arts", None) or []:
        if isinstance(a, dict) and a.get("name") == name:
            return name, sorted(int(v["v"]) for v in a.get("versions") or [] if isinstance(v, dict) and str(v.get("v")).isdigit())
    return name, []


def _version(key, have):
    """The version a key names: latest, vN or N; None when there is no such version (or the key is no key)."""
    k = str(key or "").strip()
    if k == "latest":
        return have[-1] if have else None
    m = _KEY.fullmatch(k)
    return int(m.group(1)) if m and int(m.group(1)) in have else None


def _mime(path):
    ext = posixpath.splitext(path)[1].lower()
    return "text/css" if ext == ".css" else "text/html" if ext in (".html", ".htm") else "text/plain"


def _clean_path(path):
    """The path inside a version, or None when it could leave it: a leading slash, a backslash, a NUL or a .. segment."""
    p = str(path or "")
    return None if p.startswith("/") or "\\" in p or "\x00" in p or ".." in p.split("/") else p


def site(ctx, key, path=""):
    """site/<key> (path ''): a redirect to <key>/index.html, the placeholder while nothing is built, or 404; site/<key>/<path>:
    that file of that version, 404 for any file the version does not hold."""
    try:
        name, have = _versions(ctx)
        k = str(key or "").strip()
        if not path:
            if not have:
                return _out(200, NOT_YET, "text/html") if k == "latest" or _KEY.fullmatch(k) else _gone()
            if _version(k, have) is None:
                return _gone()
            return _out(302, b"", "text/plain", Location="%s/index.html" % k)         # relative: the links inside stay in the version
        v, rel = _version(k, have), _clean_path(path)
        if v is None or rel is None:
            return _gone()
        files = W.read_files(ctx.ref, name, v)
        if rel not in files:
            return _gone()
        text = inline_css(files, rel) if rel == "index.html" else files[rel]
        return _out(200, text, _mime(rel))
    except Exception as exc:  # noqa: BLE001 -- the page shows its own empty state for a 404, never an error
        rs = getattr(ctx, "reasons", None)
        if isinstance(rs, list):
            rs.append("the site could not be read: %s" % exc)
        return _gone()


def file(ctx, name):
    return _gone()


def shot(ctx, n):
    return _gone()
