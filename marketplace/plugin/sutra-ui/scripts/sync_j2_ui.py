#!/usr/bin/env python3
"""sync_j2_ui.py -- copy the J2 prototype's page into the app, changing it by five documented substitutions only.

The owner's ruling (2026-10-26): "Take latest pull from J2 prototype and implement UI in the exact same fashion, no
change." The department screen is the prototype's page `j2_ui.html`, served from `j2ui_assets/` and fed by an adapter
built from Sutra's records. This script is the only writer of `j2ui_assets/*`.

    J2_PROTOTYPE=<repo> python3 scripts/sync_j2_ui.py [--from PATH] [--rev REV] [--check] [--check-latest]
                                                       [--no-local-fonts] [--accept-raw-interp] [--strict]

PATH comes from --from or the environment variable J2_PROTOTYPE, never from a path in this file. REV defaults to the
repo's HEAD. The files are read from git objects (`git show REV:file`), so a dirty or moved working tree changes nothing;
the prototype is never written to.

What is written (all under the app root, the folder above scripts/):
    j2ui_assets/j2_ui.html          the page, after the substitutions below
    j2ui_assets/j2_schema.py        byte for byte (the atom/1 adapter the adapter's work package imports)
    j2ui_assets/j2host.js           the one script the app adds (it only gives POSTs the panel token)
    j2ui_assets/PINNED.json         source commit and hashes, the substitutions with their positions, the app hashes
    j2ui_assets/RAW_INTERP.json     the page's template interpolations that carry no escape call (guard 5)
    test_fixtures/j2ui/j2_ui_render.js   byte for byte (a node test harness, never served)

The permitted substitutions, the only differences from the prototype's bytes in j2_ui.html (S4 and S5, A5.1.3, are kind-neutral
wording: scripts/j2ui_words_table.py holds the table, and each is the original text again when a department sets no word):
    S1  path   a quote, apostrophe or backtick followed by /api/, /site/, /file/ or /shot/ loses that first slash, so
               every URL is relative to /j2ui/{ref}/ (the page is served at a directory-style URL)
    S2  line   `<script src="j2host.js"></script>` inserted directly after the viewport meta line
    S3  fonts  the one external stylesheet's href becomes fonts/fonts.css, only when j2ui_assets/fonts/fonts.css exists
               (scripts/fetch_j2_fonts.py makes it) and --no-local-fonts is not given
    S4  words  the table WORDS of (id, original, replacement): each original occurs exactly once and is wrapped in WD(key, original)
               or escaped like it (two rows, S4.35b and S4.36b, are behaviour edits: New run and Start over)
    S5  line   `const WD = (k, d) => ...` inserted directly after `const $ = id => document.getElementById(id);`

Guards (exit 1 with a message): 1 a root-absolute URL other than api, site, file, shot; 2 S1 matched nothing; 3 an
external URL other than the one font stylesheet; 4 the viewport anchor is not found exactly once; 5 a template
interpolation without esc(, md( or plain( that RAW_INTERP.json does not hold (--accept-raw-interp acknowledges it, after
the hostile-string render test passed on the new page); 7 an S4 original does not occur exactly once; 8 a WD( in a template
interpolation that is not wrapped in esc( and is not a boolean or list key (SAFE_KEYS); 6 the page reads an api/<name> the adapter has no route for, or
a state key it does not know (a warning; exit 1 only with --strict; skipped when the adapter modules are absent).

--check writes nothing and exits 1 when the app copy differs from transform(prototype at the pinned commit).
--check-latest writes nothing and always exits 0: it says whether the prototype moved since the pin.
"""
import argparse
import datetime
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE.parent
sys.path.insert(0, str(HERE))
import j2ui_words_table as WT  # noqa: E402 -- S4 and S5, kept beside this script

PAGE, SCHEMA, RENDERER = "j2_ui.html", "j2_schema.py", "j2_ui_render.js"
SOURCES = (PAGE, SCHEMA, RENDERER)
PIN_SCHEMA = "j2ui-pin/2"
RAW_SCHEMA = "j2ui-rawinterp/1"

#: S1: the quote that opens a URL, then a slash, then the first segment the adapter answers under /j2ui/{ref}/
S1 = re.compile(rb'(["\'`])/(api|site|file|shot)/')
S1_RULE = "delete the slash in (\"|'|`)/(api|site|file|shot)/ so the URL is relative"
#: guard 1: any quote then a slash then a letter, closed by a path, query, fragment or quote (a regex literal such as
#: .replace(/`/g, "") does not match: its slash is followed by a backtick)
GUARD = re.compile(rb'(["\'`])/([A-Za-z][\w-]*)(?=[/?#"\'`])')
ROOTS = (b"api", b"site", b"file", b"shot")
S2_LINE = b'<script src="j2host.js"></script>'
S2_RULE = "insert a script line for j2host.js directly after the viewport meta line"
FONT_HREF = re.compile(rb'href="(https://fonts\.googleapis\.com/css2\?[^"]*)"')
S4_RULE = "kind-neutral wording: each listed original is wrapped in WD(key, original) or escaped like it; defaults are the originals"
S5_RULE = "insert the WD line directly after the const $ line"
S3_NEW = b"fonts/fonts.css"
S3_RULE = "the href of the one external stylesheet becomes fonts/fonts.css (vendored fonts)"
URL = re.compile(rb"https?://[^\s\"'`)<>]+")
VIEWPORT = b'<meta name="viewport"'
#: the expressions guard 5 does not list: an escape call anywhere in the expression
ESCAPES = ("esc(", "md(", "plain(")
FONT_BUDGET = 600 * 1024

J2HOST_JS = b"""/* j2host.js -- the one script the Sutra app adds around the J2 prototype's page (scripts/sync_j2_ui.py, substitution S2).
   The page is served from the app's own origin, whose guard wants the panel token on every write. This wraps fetch: a
   call that is not a GET or HEAD carries X-Sutra-Panel, and on a 403 the token is read again once and the call retried
   (the rule of apiPost in static/js/01-state.js). Nothing else. */
(function () {
  var plain = window.fetch.bind(window), token = "";
  function read(again) {
    if (token && !again) return Promise.resolve(token);
    return plain("/api/panel-token", { cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : {}; })
      .then(function (j) { token = (j && j.token) || token; return token; })
      .catch(function () { return token; });
  }
  window.fetch = function (input, init) {
    var req = input instanceof Request ? input : null;
    var method = String((init && init.method) || (req && req.method) || "GET").toUpperCase();
    if (method === "GET" || method === "HEAD") return plain(input, init);
    function send(t) {
      var h = new Headers((init && init.headers) || (req && req.headers) || {});
      h.set("X-Sutra-Panel", t);
      return plain(req ? req.clone() : input, Object.assign({}, init, { headers: h }));
    }
    return read(false).then(send).then(function (r) { return r.status === 403 ? read(true).then(send) : r; });
  };
})();
"""


class SyncError(Exception):
    """A guard fired or an input is wrong: the message says what and where; main turns it into exit 1."""


def sha(b):
    return hashlib.sha256(b).hexdigest()


def _line_col(b, offset):
    return b.count(b"\n", 0, offset) + 1, offset - (b.rfind(b"\n", 0, offset) + 1)


def transform(html, local_fonts=False):
    """The page after S1, S4, S3 (when local_fonts), S5 and S2, as bytes, with a report of what changed and where. Works on
    bytes only, so every byte it does not name is kept. Raises SyncError for guards 1 to 4, 7 and 8."""
    for m in GUARD.finditer(html):
        if m.group(2) not in ROOTS:
            ln, col = _line_col(html, m.start())
            raise SyncError("guard 1: a new root-absolute URL, %r, at line %d column %d; only api, site, file and shot are "
                            "answered under /j2ui/{ref}/" % (m.group(0).decode("utf-8", "replace"), ln, col))
    hits = list(S1.finditer(html))
    if not hits:
        raise SyncError("guard 2: S1 matched nothing; the page no longer calls /api/, /site/, /file/ or /shot/ in quotes")
    positions = [list(_line_col(html, m.start() + 1)) for m in hits]
    out = S1.sub(rb"\1\2/", html)
    out, s4 = apply_words(out)
    ext = [m.group(0) for m in URL.finditer(html)]
    extra = [u for u in ext if not FONT_HREF.search(b'href="' + u + b'"')]
    if extra:
        raise SyncError("guard 3: a new external resource, %s; the page's only external URL is its font stylesheet"
                        % extra[0].decode("utf-8", "replace"))
    report = {"s1": {"count": len(hits), "lines": sorted({p[0] for p in positions}), "positions": positions},
              "external": [u.decode("utf-8") for u in ext], "s3": None, "s4": s4}
    if local_fonts:
        found = list(FONT_HREF.finditer(out))
        if len(found) != 1:
            raise SyncError("the font stylesheet was found %d times; S3 needs exactly one" % len(found))
        m = found[0]
        report["s3"] = {"original_href": m.group(1).decode("utf-8"), "new_href": S3_NEW.decode(), "line": _line_col(out, m.start())[0]}
        out = out[:m.start(1)] + S3_NEW + out[m.end(1):]
    lines = out.splitlines(keepends=True)
    at = [i for i, ln in enumerate(lines) if VIEWPORT in ln]
    if len(at) != 1:
        raise SyncError("guard 4: the viewport meta line was found %d times; the j2host.js line goes after it, so it must "
                        "be found exactly once" % len(at))
    i = at[0]
    eol = b"\r\n" if lines[i].endswith(b"\r\n") else b"\n"
    if not lines[i].endswith(b"\n"):
        lines[i] += eol
    lines.insert(i + 1, S2_LINE + eol)
    report["s2"] = {"line": i + 1, "text": S2_LINE.decode()}
    anchor = [k for k, ln in enumerate(lines) if ln.rstrip(b"\r\n") == WT.S5_ANCHOR]
    if len(anchor) != 1:
        raise SyncError("guard 4: the line %r was found %d times; the WD line goes after it, so it must be found exactly once"
                        % (WT.S5_ANCHOR.decode(), len(anchor)))
    k = anchor[0]
    lines.insert(k + 1, WT.S5_LINE + eol)
    report["s5"] = {"line": k, "text": WT.S5_LINE.decode()}       # the anchor's line in the prototype's page (S2 sits above it)
    return b"".join(lines), report


def _in_interpolation(text, pos):
    """True when `pos` is inside a ${ ... of `text` that no } has closed since (a heuristic that is exact for the table)."""
    at = text.rfind(b"${", 0, pos)
    return at >= 0 and b"}" not in text[at:pos]


def word_problems(rows=None):
    """Guard 8 over the table: the WD( calls that sit in a template interpolation without esc( and are not a SAFE_KEYS key."""
    out = []
    for wid, _, new in (WT.WORDS if rows is None else rows):
        for m in re.finditer(rb'WD\("([a-z_]+)"', new):
            if _in_interpolation(new, m.start()) and not new[:m.start()].endswith(b"esc(") and m.group(1).decode() not in WT.SAFE_KEYS:
                out.append("guard 8: %s puts WD(%s in a template without esc(" % (wid, m.group(1).decode()))
    return out


def apply_words(page, rows=None):
    """S4 on the S1-applied page: every original exactly once (guard 7), then guard 8. Returns (page, items) where an item is
    {id, line, original, replacement} with the line of the original in the prototype's page (S1 moves no line)."""
    rows = WT.WORDS if rows is None else rows
    bad = word_problems(rows)
    if bad:
        raise SyncError(bad[0])
    items = []
    for wid, old, new in rows:
        n = page.count(old)
        if n != 1:
            raise SyncError("guard 7: %s: its original text was found %d times, it must be found exactly once: %r"
                            % (wid, n, old[:70].decode("utf-8", "replace")))
        items.append({"id": wid, "line": page.count(b"\n", 0, page.index(old)) + 1, "original": old.decode("utf-8"),
                      "replacement": new.decode("utf-8")})
    for wid, old, new in rows:
        page = page.replace(old, new, 1)
    return page, items


def raw_interpolations(html):
    """(distinct sorted list, number of uses) of the page's ${...} template expressions that hold none of esc(, md(,
    plain(, whitespace collapsed. The outer expression only: an expression nested inside another is part of it."""
    t = html.decode("utf-8")
    found, i = [], 0
    while True:
        i = t.find("${", i)
        if i < 0:
            break
        j, depth = i + 2, 1
        while j < len(t) and depth:
            depth += {"{": 1, "}": -1}.get(t[j], 0)
            j += 1
        found.append(t[i + 2:j - 1])
        i = j
    raw = [re.sub(r"\s+", " ", x).strip() for x in found if not any(k in x for k in ESCAPES)]
    return sorted(set(raw)), len(raw)


def page_contract(html, api_names, state_keys):
    """Guard 6 as a list of warnings: an api/<name> the page reads that the adapter has no route for, and an s.<key>
    the page reads that the adapter's state does not carry. Either list may be None (module absent: not checked)."""
    out = []
    if api_names is not None:
        reads = sorted({m.group(1).decode() for m in re.finditer(rb'["\'`]/?api/([a-z_]+)', html)})
        out += ["the page reads api/%s and the adapter has no route for it" % n for n in reads if n not in api_names]
    if state_keys is not None:
        keys = sorted({m.group(1).decode() for m in re.finditer(rb"\bs\.([A-Za-z_]\w*)", html)})
        out += ["the page reads s.%s and the adapter's state does not carry it" % k for k in keys if k not in state_keys]
    return out


def _adapter_names(root):
    """(api route names, state keys) from the adapter's modules in `root`, or (None, None) when they are absent."""
    if not (root / "j2ui_api.py").exists() or not (root / "j2ui_common.py").exists():
        return None, None
    sys.path.insert(0, str(root))
    try:
        import j2ui_api
        import j2ui_common
        names = {m.group(1) for r in j2ui_api.router.routes for m in [re.search(r"/api/([a-z_]+)", r.path)] if m}
        return names, set(j2ui_common.STATE_KEYS)
    except Exception:  # noqa: BLE001 -- a module that does not import is the same as an absent one for a warning
        return None, None
    finally:
        sys.path.remove(str(root))


def git(repo, *args, check=True):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    r = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, env=env)
    if check and r.returncode:
        raise SyncError("git %s failed in %s: %s" % (" ".join(args), repo, r.stderr.decode("utf-8", "replace").strip()))
    return r.stdout


def source_files(repo, rev):
    return {n: git(repo, "show", "%s:%s" % (rev, n)) for n in SOURCES}


def digest(b):
    return {"sha256": sha(b), "bytes": len(b)}


def font_files(fonts):
    """{name: bytes} of the vendored font folder; raises when fonts.css names a file that is not there."""
    css = (fonts / "fonts.css").read_bytes()
    names = [m.group(1).decode() for m in re.finditer(rb"url\(\s*['\"]?([^)'\"\s]+)", css)]
    out = {"fonts.css": css}
    for n in names:
        if not (fonts / n).is_file():
            raise SyncError("fonts/fonts.css names %s and it is not in j2ui_assets/fonts" % n)
        out[n] = (fonts / n).read_bytes()
    if "LICENSE.txt" in {p.name for p in fonts.iterdir()}:
        out["LICENSE.txt"] = (fonts / "LICENSE.txt").read_bytes()
    if sum(len(v) for v in out.values()) > FONT_BUDGET:
        raise SyncError("the vendored fonts are over %d KB" % (FONT_BUDGET // 1024))
    return out


def _load(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


def _inline(v):
    """A list of scalars, or of such lists (a column of [line, col] pairs), is short enough to stay on one line."""
    return isinstance(v, list) and all(not isinstance(x, dict) and (not isinstance(x, list) or _inline(x)) for x in v)


def _jdump(doc, depth=0):
    """json.dumps with two-space indent, but the long lists of numbers (S1's positions) kept to a line each."""
    pad = "  " * (depth + 1)
    if isinstance(doc, dict) and doc:
        rows = ["%s%s: %s" % (pad, json.dumps(k), _jdump(v, depth + 1)) for k, v in doc.items()]
        return "{\n" + ",\n".join(rows) + "\n" + "  " * depth + "}" + ("\n" if depth == 0 else "")
    if isinstance(doc, list) and doc and not _inline(doc):
        return "[\n" + ",\n".join(pad + _jdump(v, depth + 1) for v in doc) + "\n" + "  " * depth + "]"
    return json.dumps(doc, ensure_ascii=False)


def sync(root, repo, rev, local_fonts, accept, strict, out=print):
    """Write the app copy and the pin. Returns the exit code."""
    commit = git(repo, "rev-parse", "--verify", rev + "^{commit}").decode().strip()
    src = source_files(repo, commit)
    page, rep = transform(src[PAGE], local_fonts)
    distinct, uses = raw_interpolations(src[PAGE])
    rawp = root / "j2ui_assets" / "RAW_INTERP.json"
    old = _load(rawp)
    if old is not None:
        new = [x for x in distinct if x not in set(old.get("expressions") or [])]
        if new and not accept:
            out("guard 5: %d template interpolation(s) carry no esc(, md( or plain( and are not in RAW_INTERP.json:" % len(new))
            for x in new[:20]:
                out("    ${%s}" % x)
            out("run the hostile-string render test on the new page, then: --accept-raw-interp")
            return 1
    pinp = root / "j2ui_assets" / "PINNED.json"
    prev = _load(pinp) or {}
    api_names, state_keys = _adapter_names(root)
    warns = page_contract(src[PAGE], api_names, state_keys)
    if api_names is None:
        out("guard 6 skipped: the adapter modules (j2ui_api, j2ui_common) are not here yet")
    for w in warns:
        out("warning: " + w)
    if warns and strict:
        return 1
    assets = root / "j2ui_assets"
    fonts = font_files(assets / "fonts") if local_fonts else {}
    host = J2HOST_JS
    app = {"j2ui_assets/j2_ui.html": page, "j2ui_assets/j2_schema.py": src[SCHEMA], "j2ui_assets/j2host.js": host,
           "test_fixtures/j2ui/j2_ui_render.js": src[RENDERER]}
    for n, b in sorted(fonts.items()):
        app["j2ui_assets/fonts/" + n] = b
    before = (assets / PAGE).read_bytes() if (assets / PAGE).exists() else b""
    for rel, b in app.items():
        if not rel.startswith("j2ui_assets/fonts/"):
            _write(root / rel, b)
    if old is None or accept:
        _write(rawp, _jdump({"schema": RAW_SCHEMA, "commit": commit, "distinct": len(distinct), "uses": uses,
                             "expressions": distinct}))
    ack = (prev.get("raw_interp") or {}).get("acknowledged_commit")
    if accept:
        ack = commit
    subs = [{"id": "S1", "rule": S1_RULE, "count": rep["s1"]["count"], "lines": rep["s1"]["lines"], "positions": rep["s1"]["positions"]},
            {"id": "S2", "rule": S2_RULE, "line": rep["s2"]["line"], "text": rep["s2"]["text"]}]
    subs_extra = [{"id": "S4", "rule": S4_RULE, "count": len(rep["s4"]), "items": rep["s4"]},
                  {"id": "S5", "rule": S5_RULE, "line": rep["s5"]["line"], "text": rep["s5"]["text"]}]
    if rep["s3"]:
        subs.append(dict({"id": "S3", "rule": S3_RULE}, **{k: rep["s3"][k] for k in ("original_href", "new_href", "line")}))
    subs += subs_extra
    pin = {"schema": PIN_SCHEMA,
           "source": {"path": str(repo), "commit": commit, "files": {n: digest(src[n]) for n in SOURCES}},
           "app": {"files": {rel: digest(b) for rel, b in sorted(app.items())}},
           "substitutions": subs, "external": rep["external"], "local_fonts": bool(local_fonts),
           "raw_interp": {"count": len(distinct), "uses": uses, "acknowledged_commit": ack},
           "synced_at": None}
    if not local_fonts:
        pin["fonts_note"] = ("fonts not vendored: the page keeps the prototype's Google Fonts link and the page's security policy allows "
                             "its two hosts (run scripts/fetch_j2_fonts.py, then this script)")
    # a sync that changes nothing leaves the pin as it was, time included, so running it twice is no diff
    same = dict(prev, synced_at=None) == pin
    pin["synced_at"] = prev.get("synced_at") if same else datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write(pinp, _jdump(pin))
    ops = difflib.SequenceMatcher(None, before.splitlines(), page.splitlines(), autojunk=False).get_opcodes()
    moved = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in ops if tag != "equal")
    out("S1 count %d on %d lines" % (rep["s1"]["count"], len(rep["s1"]["lines"])))
    out("S2 j2host.js after line %d" % rep["s2"]["line"])
    out("S4 %d words, S5 after line %d" % (len(rep["s4"]), rep["s5"]["line"]))
    out("S3 fonts %s" % ("vendored (%s)" % ", ".join(sorted(fonts)) if rep["s3"] else "off"))
    out("%s" % ("%d line(s) differ from the previous copy" % moved if before else "first copy of the page"))
    was = (prev.get("source") or {}).get("commit")
    if was and was != commit:
        log = git(repo, "log", "--oneline", "%s..%s" % (was, commit), check=False).decode().strip()
        out("prototype %s..%s:\n%s" % (was[:7], commit[:7], log or "(no commits between)"))
    else:
        out("prototype %s" % commit[:7])
    return 0


def check(root, repo, out=print):
    """Exit 1 when the app copy differs from transform(prototype at the pinned commit); writes nothing."""
    pin = _load(root / "j2ui_assets" / "PINNED.json")
    if not pin:
        out("no j2ui_assets/PINNED.json: run: J2_PROTOTYPE=<repo> python3 scripts/sync_j2_ui.py")
        return 1
    commit = pin["source"]["commit"]
    src = source_files(repo, commit)
    page, _ = transform(src[PAGE], bool(pin.get("local_fonts")))
    bad = [rel for rel, want in (("j2ui_assets/j2_ui.html", page), ("j2ui_assets/j2_schema.py", src[SCHEMA]),
                                 ("j2ui_assets/j2host.js", J2HOST_JS), ("test_fixtures/j2ui/j2_ui_render.js", src[RENDERER]))
           if not (root / rel).exists() or (root / rel).read_bytes() != want]
    for n, want in (pin["source"]["files"]).items():
        if sha(src[n]) != want["sha256"]:
            bad.append("the pin's hash of %s is not the prototype's at %s" % (n, commit[:7]))
    for rel in bad:
        out("differs: " + rel)
    if not bad:
        out("j2ui_assets matches the prototype at %s" % commit[:7])
    return 1 if bad else 0


def check_latest(root, repo, out=print):
    """Say whether the prototype moved since the pin; always exit 0 (a report, not a gate)."""
    pin = _load(root / "j2ui_assets" / "PINNED.json")
    if not pin:
        out("no pin yet")
        return 0
    was = pin["source"]["commit"]
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    if head == was:
        out("the prototype has not moved: HEAD %s is the pin" % head[:7])
        return 0
    out("the prototype has moved: pin %s, HEAD %s" % (was[:7], head[:7]))
    out(git(repo, "log", "--oneline", "%s..%s" % (was, head), check=False).decode().strip() or "(HEAD is not ahead of the pin)")
    changed = [n for n in SOURCES if git(repo, "diff", "--name-only", was, head, "--", n, check=False).strip()]
    out("synced files changed: %s" % (", ".join(changed) or "none"))
    return 0


def main(argv=None, out=print):
    ap = argparse.ArgumentParser(prog="sync_j2_ui.py", description="Copy the J2 prototype's page into the app (S1 to S5 only).")
    ap.add_argument("--from", dest="src", help="the prototype repo (else the environment variable J2_PROTOTYPE)")
    ap.add_argument("--rev", default="HEAD", help="the prototype revision to copy (default HEAD)")
    ap.add_argument("--root", help="the app folder to write under (default: the folder above scripts/; for tests)")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if the copy differs from the pinned commit")
    ap.add_argument("--check-latest", action="store_true", help="write nothing; say whether the prototype moved; exit 0")
    ap.add_argument("--no-local-fonts", action="store_true", help="keep the prototype's Google Fonts link (S3 off)")
    ap.add_argument("--accept-raw-interp", action="store_true", help="acknowledge new unescaped interpolations (after the hostile-string test)")
    ap.add_argument("--strict", action="store_true", help="a guard 6 warning is exit 1")
    a = ap.parse_args(argv)
    path = a.src or os.environ.get("J2_PROTOTYPE")
    if not path:
        out("sync_j2_ui.py: name the prototype repo with --from PATH or the environment variable J2_PROTOTYPE")
        return 2
    repo = Path(path).expanduser().resolve()
    root = Path(a.root).resolve() if a.root else UI
    try:
        if not (repo / ".git").exists() and not git(repo, "rev-parse", "--git-dir", check=False):
            raise SyncError("%s is not a git repository" % repo)
        if a.check_latest:
            return check_latest(root, repo, out)
        if a.check:
            return check(root, repo, out)
        local = (root / "j2ui_assets" / "fonts" / "fonts.css").is_file() and not a.no_local_fonts
        return sync(root, repo, a.rev, local, a.accept_raw_interp, a.strict, out)
    except SyncError as e:
        out(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
