"""test_j2ui_sync.py -- the sync script that copies the J2 prototype's page into the app (UI-port package j2ui-shell, E1).

Named claims:
  - the corrected guard fires on a new root-absolute URL and not on a regex literal such as .replace(/`/g, ""); on the
    pinned page of the prototype (f9ceba1) the script exits 0 and counts S1 34 times on 31 lines
  - synthetic pages each exit 1: a "/foo/bar" literal, a new https://x.example URL, no viewport line, two of them, a page
    with no api path at all, a new raw ${x.name} (until --accept-raw-interp)
  - with neither --from nor J2_PROTOTYPE the script exits 2 and names the variable
  - a second run changes nothing; --check is 0 on a fresh copy and 1 after a hand edit; --check-latest always exits 0
  - the prototype's repo is never written to
  - transform keeps every byte it does not name: CRLF lines, non-ASCII text, the S1 positions in the original's coordinates
  - S3 swaps the one font href only when fonts are vendored, and names a font file that is missing
  - scripts/fetch_j2_fonts.py keeps the latin and latin-ext faces, names each file by its hash, writes fonts.css with
    relative urls and the licence, refuses a download over 600 KB, and without a network writes nothing and exits 3

The prototype is read only; the tests that need it skip with a printed reason when it is not there.
Run: ./run-tests.sh test_j2ui_sync.py"""
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent
SCRIPT = UI / "scripts" / "sync_j2_ui.py"
FETCH = UI / "scripts" / "fetch_j2_fonts.py"
PIN = json.loads((UI / "j2ui_assets" / "PINNED.json").read_text()) if (UI / "j2ui_assets" / "PINNED.json").exists() else {}


def _load():
    spec = importlib.util.spec_from_file_location("sync_j2_ui", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_j2_ui"] = mod
    spec.loader.exec_module(mod)
    return mod


SYNC = _load()


def _load_fetch():
    spec = importlib.util.spec_from_file_location("fetch_j2_fonts", FETCH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fetch_j2_fonts"] = mod
    spec.loader.exec_module(mod)
    return mod


FETCHER = _load_fetch()

FONT = "https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600&family=IBM+Plex+Sans:wght@400&display=swap"
GOOD = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>T</title>\n'
        '<link rel="stylesheet" href="%s">\n<script>\n'
        'const a = await fetch("/api/state?since=0"), b = `/site/latest`, c = "x".replace(/`/g, "");\n'
        'const d = ["/file/x.md", \'/shot/8\'].map(u => u + "/api/map");\n'
        '</script>\n</head>\n<body><div>${esc(a)} ${md(b)}</div></body>\n</html>\n') % FONT


def _repo(tmp_path, page=GOOD, name="proto"):
    """A throwaway git repo holding the three files the script reads, one commit; returns (path, sha)."""
    repo = tmp_path / name
    repo.mkdir()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.test", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@example.test")
    run = lambda *a: subprocess.run(["git", "-C", str(repo)] + list(a), check=True, capture_output=True, env=env)
    run("init", "-q")
    _put(repo, page)
    run("add", "-A")
    run("commit", "-q", "-m", "first")
    return repo, run("rev-parse", "HEAD").stdout.decode().strip(), run


def _put(repo, page):
    data = page if isinstance(page, bytes) else page.encode("utf-8")
    (repo / "j2_ui.html").write_bytes(data)
    (repo / "j2_schema.py").write_text("SCHEMA = 1\n")
    (repo / "j2_ui_render.js").write_text("// harness\n")


def _sync(root, repo, *flags):
    lines = []
    code = SYNC.main(["--from", str(repo), "--root", str(root)] + list(flags), out=lines.append)
    return code, "\n".join(lines)


def _restore(app, pin):
    """The prototype's page from the app's copy and the pin: the S2 line out, the S3 href back, the S1 slashes in at their
    columns (original coordinates, so the first of a line goes in first)."""
    lines = app.splitlines(keepends=True)
    gone = [i for i, ln in enumerate(lines) if ln.strip() == b'<script src="j2host.js"></script>']
    assert len(gone) == 1
    del lines[gone[0]]
    subs = {s["id"]: s for s in pin["substitutions"]}
    if "S3" in subs:
        lines = [ln.replace(subs["S3"]["new_href"].encode(), subs["S3"]["original_href"].encode()) for ln in lines]
    for line, col in sorted(subs["S1"]["positions"]):
        ln = lines[line - 1]
        lines[line - 1] = ln[:col] + b"/" + ln[col:]
    return b"".join(lines)


def _proto():
    """The prototype repo when it is there and holds the pinned commit; else the reason to skip."""
    path = os.environ.get("J2_PROTOTYPE") or (PIN.get("source") or {}).get("path")
    if not path or not (Path(path) / ".git").exists():
        pytest.skip("the prototype repo is not here (set J2_PROTOTYPE)")
    have = subprocess.run(["git", "-C", path, "cat-file", "-e", PIN["source"]["commit"] + "^{commit}"], capture_output=True)
    if have.returncode:
        pytest.skip("the prototype repo does not hold the pinned commit " + PIN["source"]["commit"][:7])
    return Path(path)


# ── the guard and the substitutions on the real page ──────────────────────────────────────────────────────────────
def test_the_guard_exits_0_on_the_pinned_page_and_counts_34_on_31_lines():
    page = _restore((UI / "j2ui_assets" / "j2_ui.html").read_bytes(), PIN)
    out, rep = SYNC.transform(page)
    assert rep["s1"]["count"] == 34 and len(rep["s1"]["lines"]) == 31
    by = {}
    for m in SYNC.S1.finditer(page):
        by[m.group(2)] = by.get(m.group(2), 0) + 1
    assert by == {b"api": 18, b"site": 8, b"file": 7, b"shot": 1}
    assert not SYNC.S1.search(out) and out.count(b'<script src="j2host.js"></script>') == 1
    assert not [m for m in SYNC.GUARD.finditer(page) if m.group(2) not in SYNC.ROOTS], "the regex literal on line 595 is not a URL"


def test_the_script_on_the_pinned_commit_of_the_prototype_exits_0_and_leaves_the_prototype_alone(tmp_path):
    proto = _proto()
    before = subprocess.run(["git", "-C", str(proto), "status", "--short"], capture_output=True, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0")).stdout
    code, said = _sync(tmp_path, proto, "--rev", PIN["source"]["commit"])
    assert code == 0, said
    assert "S1 count 34 on 31 lines" in said
    after = subprocess.run(["git", "-C", str(proto), "status", "--short"], capture_output=True, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0")).stdout
    assert after == before, "the prototype's working tree is the same after the run"
    mine = json.loads((tmp_path / "j2ui_assets" / "PINNED.json").read_text())
    assert mine["source"]["files"]["j2_ui.html"]["sha256"] == "23549799903e98485f404872670c49e5735c7cc9962c19b42037b1bde5ebad0d"
    assert mine["source"]["files"]["j2_ui_render.js"]["sha256"] == "d65cf52fcf4cc2dafd70dcb7ac2a963be5508ba70531176a4fa4aaff0ed251f4"
    assert (tmp_path / "j2ui_assets" / "j2_ui.html").read_bytes() == (UI / "j2ui_assets" / "j2_ui.html").read_bytes()
    assert mine["raw_interp"]["count"] == 569 and mine["raw_interp"]["uses"] == 813


# ── synthetic pages: each guard exits 1 ───────────────────────────────────────────────────────────────────────────
def test_a_good_synthetic_page_syncs(tmp_path):
    repo, sha, _ = _repo(tmp_path)
    code, said = _sync(tmp_path / "app", repo)
    assert code == 0, said
    pin = json.loads((tmp_path / "app" / "j2ui_assets" / "PINNED.json").read_text())
    s1 = [s for s in pin["substitutions"] if s["id"] == "S1"][0]
    assert s1["count"] == 5 and pin["source"]["commit"] == sha and pin["local_fonts"] is False
    page = (tmp_path / "app" / "j2ui_assets" / "j2_ui.html").read_text()
    assert page.count('<script src="j2host.js"></script>') == 1 and '"api/state?since=0"' in page and "`site/latest`" in page
    assert ".replace(/`/g" in page, "a regex literal is not a URL"


@pytest.mark.parametrize("what, page, word", [
    ("a root-absolute literal", GOOD.replace('"x"', '"/foo/bar"'), "guard 1"),
    ("a new external URL", GOOD.replace("<title>T</title>", '<title>T</title><img src="https://x.example/a.png">'), "guard 3"),
    ("no viewport line", GOOD.replace('<meta name="viewport" content="width=device-width, initial-scale=1">\n', ""), "guard 4"),
    ("two viewport lines", GOOD.replace("<title>T</title>", '<meta name="viewport" content="x">\n<title>T</title>'), "guard 4"),
    ("no api path at all", re.sub(r'(["\'`])/(api|site|file|shot)/', r"\1\2/", GOOD), "guard 2"),
])
def test_each_synthetic_guard_exits_1(tmp_path, what, page, word):
    repo, _, _ = _repo(tmp_path, page)
    code, said = _sync(tmp_path / "app", repo)
    assert code == 1 and word in said, what + ": " + said
    assert not (tmp_path / "app" / "j2ui_assets" / "j2_ui.html").exists(), "a refused page writes nothing"


def test_a_new_raw_interpolation_exits_1_until_it_is_accepted(tmp_path):
    repo, _, run = _repo(tmp_path)
    assert _sync(tmp_path / "app", repo)[0] == 0
    _put(repo, GOOD.replace("${esc(a)}", "${esc(a)} ${x.name}"))
    run("commit", "-q", "-am", "adds a raw one")
    code, said = _sync(tmp_path / "app", repo)
    assert code == 1 and "guard 5" in said and "${x.name}" in said and "--accept-raw-interp" in said
    code, said = _sync(tmp_path / "app", repo, "--accept-raw-interp")
    assert code == 0, said
    pin = json.loads((tmp_path / "app" / "j2ui_assets" / "PINNED.json").read_text())
    assert pin["raw_interp"]["acknowledged_commit"] == pin["source"]["commit"]
    assert _sync(tmp_path / "app", repo)[0] == 0, "once acknowledged it is known"


def test_without_a_prototype_the_script_exits_2_and_names_the_variable(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "J2_PROTOTYPE"}
    r = subprocess.run([sys.executable, str(SCRIPT), "--root", str(tmp_path)], capture_output=True, env=env, cwd=str(tmp_path))
    assert r.returncode == 2 and b"J2_PROTOTYPE" in r.stdout


def test_the_script_has_no_path_of_the_owners_machine_in_it():
    assert "/Users/" not in SCRIPT.read_text()


# ── idempotence, --check, --check-latest ──────────────────────────────────────────────────────────────────────────
def test_a_second_run_changes_nothing_and_check_reads_the_copy(tmp_path):
    repo, sha, run = _repo(tmp_path)
    app = tmp_path / "app"
    assert _sync(app, repo)[0] == 0
    snap = {p: p.read_bytes() for p in app.rglob("*") if p.is_file()}
    assert _sync(app, repo)[0] == 0
    assert {p: p.read_bytes() for p in app.rglob("*") if p.is_file()} == snap, "running it twice is no diff"
    assert _sync(app, repo, "--check")[0] == 0
    # the prototype moves on: --check still reads the pinned commit; --check-latest reports and exits 0
    _put(repo, GOOD.replace("<title>T</title>", "<title>U</title>"))
    run("commit", "-q", "-am", "retitle")
    assert _sync(app, repo, "--check")[0] == 0
    code, said = _sync(app, repo, "--check-latest")
    assert code == 0 and "has moved" in said and "retitle" in said and "j2_ui.html" in said
    assert {p: p.read_bytes() for p in app.rglob("*") if p.is_file()} == snap, "--check and --check-latest write nothing"
    # a hand edit of the copy is caught
    p = app / "j2ui_assets" / "j2_ui.html"
    p.write_bytes(p.read_bytes().replace(b"<title>T", b"<title>Z"))
    code, said = _sync(app, repo, "--check")
    assert code == 1 and "j2_ui.html" in said


def test_check_latest_says_not_moved_when_it_has_not_and_never_fails(tmp_path):
    repo, _, _ = _repo(tmp_path)
    app = tmp_path / "app"
    assert _sync(app, repo, "--check-latest")[0] == 0, "no pin yet is still a report"
    assert _sync(app, repo)[0] == 0
    code, said = _sync(app, repo, "--check-latest")
    assert code == 0 and "has not moved" in said


# ── transform: the bytes it does not name are kept ────────────────────────────────────────────────────────────────
def test_transform_keeps_crlf_and_non_ascii_and_records_columns_in_the_originals_coordinates():
    page = GOOD.replace("\n", "\r\n").replace("<title>T", "<title>café — T").encode("utf-8")
    out, rep = SYNC.transform(page)
    assert b'<script src="j2host.js"></script>\r\n' in out and out.count(b"\r\n") == page.count(b"\r\n") + 1
    assert "café — T".encode() in out
    # line 10 holds three slashes to delete: the recorded columns are the original's, so the first goes in first
    three = [p for p in rep["s1"]["positions"] if p[0] == 10]
    assert len(three) == 3
    assert [page.splitlines(keepends=True)[9][c:c + 1] for _, c in three] == [b"/", b"/", b"/"]
    back = _restore_lines(out, rep)
    assert back == page


def _restore_lines(out, rep):
    lines = out.splitlines(keepends=True)
    del lines[rep["s2"]["line"]]
    for line, col in sorted(rep["s1"]["positions"]):
        lines[line - 1] = lines[line - 1][:col] + b"/" + lines[line - 1][col:]
    return b"".join(lines)


def test_page_contract_names_a_route_or_a_state_key_the_adapter_lacks():
    html = b'fetch("api/state"); fetch(`api/newthing`); x = s.chat + s.brandnew;'
    assert SYNC.page_contract(html, {"state"}, {"chat"}) == [
        "the page reads api/newthing and the adapter has no route for it", "the page reads s.brandnew and the adapter's state does not carry it"]
    assert SYNC.page_contract(html, None, None) == [], "absent modules: nothing to compare"


# ── S3: the vendored fonts ────────────────────────────────────────────────────────────────────────────────────────
def test_s3_swaps_the_one_font_href_only_when_asked():
    page = GOOD.encode()
    off, rep = SYNC.transform(page, False)
    on, rep3 = SYNC.transform(page, True)
    assert FONT.encode() in off and rep["s3"] is None
    assert FONT.encode() not in on and b'href="fonts/fonts.css"' in on
    assert rep3["s3"] == {"original_href": FONT, "new_href": "fonts/fonts.css", "line": 7}
    with pytest.raises(SYNC.SyncError, match="font stylesheet"):
        SYNC.transform(GOOD.replace(FONT, "x.css").encode(), True)


def test_a_vendored_font_folder_switches_s3_on_and_a_missing_file_is_refused(tmp_path):
    repo, _, _ = _repo(tmp_path)
    app = tmp_path / "app"
    fonts = app / "j2ui_assets" / "fonts"
    fonts.mkdir(parents=True)
    (fonts / "fonts.css").write_text("@font-face{font-family:X;src:url(x-latin.woff2) format('woff2')}\n")
    code, said = _sync(app, repo)
    assert code == 1 and "x-latin.woff2" in said and "not in j2ui_assets/fonts" in said
    (fonts / "x-latin.woff2").write_bytes(b"wOF2 test bytes")
    code, said = _sync(app, repo)
    assert code == 0 and "S3 fonts vendored" in said
    pin = json.loads((app / "j2ui_assets" / "PINNED.json").read_text())
    s3 = [s for s in pin["substitutions"] if s["id"] == "S3"][0]
    assert s3["original_href"] == FONT and pin["local_fonts"] is True
    assert "j2ui_assets/fonts/x-latin.woff2" in pin["app"]["files"] and "j2ui_assets/fonts/fonts.css" in pin["app"]["files"]
    assert b'href="fonts/fonts.css"' in (app / "j2ui_assets" / "j2_ui.html").read_bytes()
    code, said = _sync(app, repo, "--no-local-fonts")
    assert code == 0 and "S3 fonts off" in said
    assert FONT.encode() in (app / "j2ui_assets" / "j2_ui.html").read_bytes()


# ── scripts/fetch_j2_fonts.py (offline: the network is a stub) ─────────────────────────────────────────────────────
GCSS = """/* cyrillic */
@font-face {
  font-family: 'IBM Plex Sans';
  font-style: normal;
  font-weight: 400;
  src: url(https://fonts.gstatic.com/s/ibmplexsans/v1/cyr.woff2) format('woff2');
  unicode-range: U+0301;
}
/* latin-ext */
@font-face {
  font-family: 'IBM Plex Sans';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/ibmplexsans/v1/ext.woff2) format('woff2');
  unicode-range: U+0100-02BA;
}
/* latin */
@font-face {
  font-family: 'IBM Plex Sans';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/ibmplexsans/v1/lat.woff2) format('woff2');
  unicode-range: U+0000-00FF;
}
/* latin */
@font-face {
  font-family: 'IBM Plex Sans';
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/ibmplexsans/v1/lat.woff2) format('woff2');
  unicode-range: U+0000-00FF;
}
"""


def _stub(sizes=None):
    seen = []

    def fetch(url):
        seen.append(url)
        if url.endswith("css2?family=IBM+Plex+Sans"):
            return GCSS.encode()
        return (b"wOF2" + url.encode()).ljust((sizes or {}).get(url.rsplit("/", 1)[-1], 40), b".")
    return fetch, seen


def test_the_fetch_script_keeps_the_latin_faces_names_files_by_hash_and_writes_the_licence(tmp_path):
    fetch, seen = _stub()
    files, families = FETCHER.vendor("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans", fetch)
    assert families == ["IBM Plex Sans"]
    woff = sorted(n for n in files if n.endswith(".woff2"))
    assert len(woff) == 2 and all(re.fullmatch(r"ibm-plex-sans-(latin|latin-ext)-[0-9a-f]{8}\.woff2", n) for n in woff)
    assert not any("cyr" in u for u in seen), "a subset that is not kept is never downloaded"
    assert len([u for u in seen if u.endswith("lat.woff2")]) == 1, "two weights, one file: downloaded once"
    css = files["fonts.css"].decode()
    assert css.count("@font-face") == 3 and "gstatic" not in css.split("*/", 1)[1] and "font-weight:500" in css.replace(" ", "")
    assert all(("url(%s)" % n) in css for n in woff)
    lic = files["LICENSE.txt"].decode()
    assert "SIL OPEN FONT LICENSE Version 1.1" in lic and "IBM Plex Sans" in lic and "css2?family=IBM+Plex+Sans" in lic


def test_the_fetch_script_writes_a_folder_the_sync_then_pins(tmp_path):
    repo, _, _ = _repo(tmp_path)
    app = tmp_path / "app"
    assert _sync(app, repo)[0] == 0
    pin = app / "j2ui_assets" / "PINNED.json"
    doc = json.loads(pin.read_text())
    doc["external"] = ["https://fonts.googleapis.com/css2?family=IBM+Plex+Sans"]
    pin.write_text(json.dumps(doc))
    said = []
    fetch, _ = _stub()
    assert FETCHER.main(["--root", str(app)], said.append, fetch) == 0, said
    folder = app / "j2ui_assets" / "fonts"
    assert (folder / "fonts.css").exists() and (folder / "LICENSE.txt").exists() and len(list(folder.glob("*.woff2"))) == 2
    assert sum(p.stat().st_size for p in folder.iterdir()) < 600 * 1024
    code, out = _sync(app, repo)
    assert code == 0 and "S3 fonts vendored" in out, out
    css = (folder / "fonts.css").read_text()
    assert all((folder / m).is_file() for m in re.findall(r"url\(([^)]+)\)", css)), "fonts.css names only files that are there"
    again = json.loads(pin.read_text())
    assert again["local_fonts"] is True and [s["id"] for s in again["substitutions"]] == ["S1", "S2", "S3"]


def test_without_a_network_the_fetch_script_writes_nothing_and_exits_3(tmp_path):
    def offline(url):
        raise FETCHER.FetchError("fonts not vendored: no network (test)")
    said = []
    code = FETCHER.main(["--root", str(tmp_path), "--css-url", "https://fonts.googleapis.com/css2?family=X"], said.append, offline)
    assert code == 3 and "no network" in said[0]
    assert not (tmp_path / "j2ui_assets").exists()


def test_the_fetch_script_refuses_fonts_over_the_budget_and_a_stylesheet_with_no_latin_face(tmp_path):
    fetch, _ = _stub({"lat.woff2": 700 * 1024})
    with pytest.raises(FETCHER.FetchError, match="budget"):
        FETCHER.vendor("https://fonts.googleapis.com/css2?family=IBM+Plex+Sans", fetch)
    with pytest.raises(FETCHER.FetchError, match="no latin"):
        FETCHER.vendor("x", lambda u: b"/* cyrillic */ @font-face { font-family: 'A'; src: url(a.woff2) format('woff2'); }")
    assert FETCHER.main(["--root", str(tmp_path)], lambda *_: None) == 2, "no pin and no --css-url"
