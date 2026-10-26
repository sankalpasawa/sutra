"""j2ui_artifacts.py -- the J2 page's Artifacts tab (artifacts/1), listed from the department's own record.

The page (the J2 prototype's j2_ui.html, copied whole) lists a run's artifacts from /api/artifacts and opens one through
/api/artifact?name=<file>. This module is those two reads for a department of kind website, from the Ctx contract
(j2ui_common, built by j2ui-core): `ctx.arts` is the line's artifacts in order, each with its version rows; a version's
files come from website_dept.read_files. It writes nothing and calls no model.

  listing(ctx)           {deliverables: [row], records: [row]}; the previewable artifact and the Live site are the
                         deliverables, every other artifact is a record; an artifact with no version has no row
  served(ctx, name)      (bytes, mime) for a file the listing names, else None: nothing else is ever served, and a
                         path is never built from `name` (it is looked up among the listed files)
  previewable(ctx)       the artifact the Preview tab shows: Build, else the last artifact of the line
  primary(files)         the file a row opens: index.html, else the first .md, else the first file by name
  tag_of(name, primary)  the row's tag and colour token
  inline_css(files, name) a page with its style.css inlined, so a sandboxed frame is styled in every shell

Every builder memoises on ctx.memo and never raises: a failed read gives the empty shape and a reason in ctx.reasons.
Whatever a model or an engine wrote is served by the router with website_api.SAFE (no script runs, opaque origin).
"""
import hashlib
import posixpath
import re

import website_dept as W

MAX_BYTES = 2_000_000                       # the prototype's j2_artifacts.MAX_BYTES: a larger file is not served
OPEN = {"doc": "text", "data": "text", "page": "preview", "image": "image"}      # how the Artifacts tab shows a form (this adapter makes no image rows)
ROW_KEYS = ("name", "type", "kind", "form", "file", "deliverable", "workflows", "depends_on", "version", "sha256", "time",
            "label", "tag", "color", "open", "depends_on_labels", "saved")
LIVE = "Live site"                           # the second deliverable: what the Publish engine filed
PREVIEW = "Build"                            # the artifact the Preview tab shows when the line has one
_HTML = (".html", ".htm")
_DOC = (".md", ".txt")


def _memo(ctx):
    m = getattr(ctx, "memo", None)
    return m if isinstance(m, dict) else {}


def _reason(ctx, why):
    rs = getattr(ctx, "reasons", None)
    if isinstance(rs, list) and why not in rs:
        rs.append(why)


def _ext(name):
    return posixpath.splitext(str(name or ""))[1].lower()


def previewable(ctx):
    """The artifact the Preview tab shows: Build, else the last artifact of the line ('' when the line has none)."""
    names = [a.get("name") for a in getattr(ctx, "arts", None) or [] if isinstance(a, dict) and a.get("name")]
    return PREVIEW if PREVIEW in names else (names[-1] if names else "")


def primary(files):
    """The file a row opens: index.html, else the first .md, else the first file by name ('' for no files)."""
    names = sorted(files or {})
    if "index.html" in names:
        return "index.html"
    return next((n for n in names if _ext(n) == ".md"), names[0] if names else "")


def form_of(name, text=""):
    """page for markup, doc for .md and .txt, data for the rest. A file named .html that holds data (the Pages record keeps
    each page as JSON under an .html name) is data: the page shows it as text, not as a broken page."""
    e = _ext(name)
    if e in _HTML:
        return "page" if str(text or "").lstrip("﻿ \t\r\n").startswith("<") else "data"
    return "doc" if e in _DOC else "data"


def tag_of(name, primary_name, prev=None):
    """('Site', '--site') for the previewable artifact and the Live site when the file it opens is html, else ('Other',
    '--other'). `prev` is previewable(ctx); without it the previewable artifact is taken to be Build."""
    site = name in (prev or PREVIEW, LIVE) and _ext(primary_name) in _HTML
    return ("Site", "--site") if site else ("Other", "--other")


_TAG = re.compile(r"<link\b[^>]*>", re.I)
_REL = re.compile(r"""\brel\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_HREF = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)


def _attr(rx, tag):
    m = rx.search(tag)
    return next((g for g in m.groups() if g is not None), "") if m else ""


def inline_css(files, html_name):
    """The page `html_name` with its stylesheet link replaced by an inline <style> of the version's style.css (either
    attribute order); the document is left alone when it has no such link or the version has no style.css."""
    text = (files or {}).get(html_name)
    if not isinstance(text, str):
        return ""
    css = (files or {}).get(posixpath.normpath(posixpath.join(posixpath.dirname(html_name), "style.css")))
    if not isinstance(css, str):
        return text
    safe = re.sub(r"</(style)", r"<\\/\1", css, flags=re.I)         # the css can never close its own tag

    def swap(m):
        tag = m.group(0)
        href = _attr(_HREF, tag)
        if "stylesheet" in _attr(_REL, tag).lower().split() and href in ("style.css", "./style.css"):
            return "<style>" + safe + "</style>"
        return tag
    return _TAG.sub(swap, text)


def _build(ctx):
    arts = [a for a in getattr(ctx, "arts", None) or [] if isinstance(a, dict) and a.get("name")]
    prev = previewable(ctx)
    keep = {prev, LIVE}
    writer = {e.get("writes"): e for e in getattr(ctx, "engines", None) or [] if isinstance(e, dict) and e.get("writes")}
    made = {}
    for a in arts:
        vs = [v for v in a.get("versions") or [] if isinstance(v, dict) and v.get("v") is not None]
        if not vs:
            continue
        v = vs[-1]
        files = W.read_files(ctx.ref, a["name"], v["v"])
        prim = primary(files)
        if not prim:
            _reason(ctx, "%s v%s has no file to open" % (a["name"], v["v"]))
            continue
        made[a["name"]] = (a, v, files, prim)
    out, index = {"deliverables": [], "records": []}, {}
    for a in arts:
        if a["name"] not in made:
            continue
        _, v, files, prim = made[a["name"]]
        text = files[prim]
        form = form_of(prim, text)
        eng = writer.get(a["name"])
        dep = eng.get("reads") if eng else None
        dep_art = made[dep][0] if dep in made else None
        tag, color = tag_of(a["name"], prim, prev)
        if form != "page":
            tag, color = "Other", "--other"
        deliver = a["name"] in keep
        file = "%s/v%s/%s" % (a.get("slug") or W.slug(a["name"]), v["v"], prim)
        row = {"name": a["name"], "type": a.get("slug") or W.slug(a["name"]), "kind": "type" if deliver else "record", "form": form,
               "file": file, "deliverable": deliver, "workflows": [eng["wid"]] if eng and eng.get("wid") else [],
               "depends_on": [dep_art.get("slug") or W.slug(dep_art["name"])] if dep_art else [], "version": v["v"],
               "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "time": str(v.get("at") or ""),
               "label": a["name"], "tag": tag, "color": color, "open": OPEN[form],
               "depends_on_labels": [dep_art["name"]] if dep_art else [], "saved": True}
        out["deliverables" if deliver else "records"].append(row)
        index[file] = (a["name"], v["v"], prim)
    return out, index


def _read(ctx):
    memo = _memo(ctx)
    if "artifacts" not in memo:
        try:
            memo["artifacts"] = _build(ctx)
        except Exception as exc:  # noqa: BLE001 -- the page blanks on a wrong shape: the empty one, and why
            _reason(ctx, "the artifacts could not be read: %s" % exc)
            memo["artifacts"] = ({"deliverables": [], "records": []}, {})
    return memo["artifacts"]


def listing(ctx):
    """What the Artifacts tab shows: {deliverables: [row], records: [row]}, each row the prototype's 17 keys."""
    return _read(ctx)[0]


def served(ctx, name):
    """(bytes, mime) of the file the listing names `name`, else None. The exact string must be a listed file, so a path
    with .., a leading slash, a backslash, an encoded dot, an unlisted file of a listed version or a file over
    MAX_BYTES is None. A page comes with its stylesheet inlined; whatever it holds is returned as written."""
    try:
        if not isinstance(name, str) or not name or "\\" in name or "\x00" in name or name.startswith("/"):
            return None
        hit = _read(ctx)[1].get(name)
        if not hit or ".." in name.split("/"):
            return None
        art, v, prim = hit
        files = W.read_files(ctx.ref, art, v)
        text = files.get(prim)
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
            return None
        if form_of(prim, text) == "page":
            data, mime = inline_css(files, prim).encode("utf-8"), "text/html"
        else:
            data, mime = text.encode("utf-8"), "text/plain"
        return (data, mime) if len(data) <= MAX_BYTES else None
    except Exception as exc:  # noqa: BLE001 -- a file that cannot be read is not served
        _reason(ctx, "a file could not be served: %s" % exc)
        return None
