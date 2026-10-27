"""test_j2ui_verbatim.py -- the department's page is the J2 prototype's page, changed by the documented substitutions only.

The owner's requirement (2026-10-26): "Take latest pull from J2 prototype and implement UI in the exact same fashion, no
change." The page in j2ui_assets/ is scripts/sync_j2_ui.py's copy of the prototype's j2_ui.html (substitutions S1 relative
paths, S2 one script line, S3 fonts when vendored). Three layers, so the test protects the default run without making
the publish gate depend on a sibling checkout:

  1. HERMETIC, always: the copy with its S1 slashes put back at the pinned columns, its S2 line taken out and its S3
     href restored hashes to the prototype's own sha256 in PINNED.json; every app file hashes to PINNED.app;
     j2_schema.py and the render harness hash to the pinned source hashes; j2host.js names no URL but /api/panel-token.
  2. AGAINST THE PINNED COMMIT, when the prototype repo holds it (git objects, never the working tree): the sync
     script's transform of the prototype's page equals the copy byte for byte; an independent difflib check of the
     lines (only S1 lines, the S3 href line and one inserted S2 line; nothing deleted); the two byte copies are the
     pinned objects.
  3. "The prototype has moved" is a report, not a failure: --check-latest exits 0.

A check that cannot fail is no test, so each check is a function and a test hands it a hand-edited page.
A failure ends: run: J2_PROTOTYPE=<repo> python3 scripts/sync_j2_ui.py
Run: ./run-tests.sh test_j2ui_verbatim.py        (J2_PROTOTYPE=<repo> adds layer 2)"""
import difflib
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent
ASSETS = UI / "j2ui_assets"
SCRIPT = UI / "scripts" / "sync_j2_ui.py"
PIN = json.loads((ASSETS / "PINNED.json").read_text())
FIX = "run: J2_PROTOTYPE=<repo> python3 scripts/sync_j2_ui.py"
PAGE_SHA = "23549799903e98485f404872670c49e5735c7cc9962c19b42037b1bde5ebad0d"
RENDER_SHA = "d65cf52fcf4cc2dafd70dcb7ac2a963be5508ba70531176a4fa4aaff0ed251f4"
S1 = re.compile(rb'(["\'`])/(api|site|file|shot)/')
S2_LINE = b'<script src="j2host.js"></script>'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def fail(problems):
    pytest.fail("\n".join(problems) + "\n" + FIX, pytrace=False)


def subs(pin=PIN):
    return {s["id"]: s for s in pin["substitutions"]}


# ── layer 1: the hermetic checks, as functions of bytes ───────────────────────────────────────────────────────────
def restore(app, pin=PIN):
    """The prototype's page from the copy: the S2 line out, the S3 href back, the S1 slashes in at the pinned columns
    (original coordinates, so within a line the first goes in first and the others keep their columns)."""
    s = subs(pin)
    lines = app.splitlines(keepends=True)
    at = [i for i, ln in enumerate(lines) if ln.rstrip(b"\r\n") == s["S2"]["text"].encode()]
    if len(at) != 1:
        return None
    del lines[at[0]]
    if "S3" in s:
        lines = [ln.replace(s["S3"]["new_href"].encode(), s["S3"]["original_href"].encode()) for ln in lines]
    for line, col in sorted(s["S1"]["positions"]):
        ln = lines[line - 1]
        lines[line - 1] = ln[:col] + b"/" + ln[col:]
    return b"".join(lines)


def page_problems(app, pin=PIN):
    back = restore(app, pin)
    if back is None:
        return ["j2ui_assets/j2_ui.html: the j2host.js line is not there exactly once"]
    want = pin["source"]["files"]["j2_ui.html"]["sha256"]
    if sha(back) != want:
        return ["j2ui_assets/j2_ui.html is not the prototype's page plus the documented substitutions: with S1, S2 and S3 undone "
                "its sha256 is %s, the pin says %s" % (sha(back), want)]
    return []


def app_problems(root=UI, pin=PIN):
    out = []
    for rel, want in pin["app"]["files"].items():
        p = root / rel
        if not p.is_file():
            out.append("%s is missing" % rel)
        elif sha(p.read_bytes()) != want["sha256"]:
            out.append("%s differs from the pin" % rel)
    return out


def host_problems(js):
    urls = set(re.findall(rb"https?://[^\s\"'`)]+", js)) | {m for m in re.findall(rb"[\"'`](/[A-Za-z][^\"'`\s]*)[\"'`]", js)}
    return ["j2host.js names %s; its only URL is /api/panel-token" % sorted(u.decode() for u in urls - {b"/api/panel-token"})] \
        if urls - {b"/api/panel-token"} else []


def test_the_pin_is_well_formed():
    assert PIN["schema"] == "j2ui-pin/1" and re.fullmatch(r"[0-9a-f]{40}", PIN["source"]["commit"])
    s = subs()
    assert s["S1"]["count"] == len(s["S1"]["positions"]) == 34 and len(s["S1"]["lines"]) == 31
    assert sorted({p[0] for p in s["S1"]["positions"]}) == s["S1"]["lines"]
    assert s["S2"]["text"] == S2_LINE.decode() and s["S2"]["line"] == 5
    assert ("S3" in s) == PIN["local_fonts"], "S3 is listed exactly when the fonts are vendored"
    if "S3" in s:
        assert s["S3"]["original_href"].startswith("https://fonts.googleapis.com/css2?") and s["S3"]["new_href"] == "fonts/fonts.css"
    assert len(PIN["external"]) == 1 and (s["S3"]["original_href"] == PIN["external"][0] if "S3" in s else True)


def test_hermetic_the_copy_with_its_substitutions_undone_is_the_prototypes_page():
    problems = page_problems((ASSETS / "j2_ui.html").read_bytes())
    if problems:
        fail(problems)
    assert PIN["source"]["files"]["j2_ui.html"]["sha256"] == PAGE_SHA


def test_hermetic_every_app_file_is_the_one_pinned_and_the_byte_copies_are_the_prototypes():
    problems = app_problems()
    if problems:
        fail(problems)
    src = PIN["source"]["files"]
    assert sha((ASSETS / "j2_schema.py").read_bytes()) == src["j2_schema.py"]["sha256"], "j2_schema.py is a byte copy"
    assert sha((UI / "test_fixtures" / "j2ui" / "j2_ui_render.js").read_bytes()) == src["j2_ui_render.js"]["sha256"] == RENDER_SHA


def test_hermetic_j2host_names_no_url_but_the_panel_token():
    problems = host_problems((ASSETS / "j2host.js").read_bytes())
    if problems:
        fail(problems)
    assert b"/api/panel-token" in (ASSETS / "j2host.js").read_bytes()


def test_hermetic_the_copy_adds_nothing_the_pin_does_not_name():
    app = (ASSETS / "j2_ui.html").read_bytes()
    assert not S1.search(app), "no quote-slash-api left: every URL is relative"
    assert app.count(S2_LINE) == 1
    # the copy is the original's size, less one byte per S1 slash, plus the S2 line, plus the S3 swap when it is on
    s = subs()
    grow = len(S2_LINE) + 1 - s["S1"]["count"]
    if "S3" in s:
        grow += len(s["S3"]["new_href"]) - len(s["S3"]["original_href"])
    assert len(app) == PIN["source"]["files"]["j2_ui.html"]["bytes"] + grow


# ── the checks can fail: a hand-edited page is caught ─────────────────────────────────────────────────────────────
def test_a_hand_edit_of_one_character_is_caught_by_the_hermetic_check():
    app = bytearray((ASSETS / "j2_ui.html").read_bytes())
    i = app.index(b"J2 Department")
    app[i] = ord("j")
    problems = page_problems(bytes(app))
    assert problems and "sha256" in problems[0]
    with pytest.raises(pytest.fail.Exception, match=r"run: J2_PROTOTYPE=<repo> python3 scripts/sync_j2_ui\.py$"):
        fail(problems)


def test_a_lost_substitution_or_an_extra_line_is_caught():
    app = (ASSETS / "j2_ui.html").read_bytes()
    assert page_problems(app.replace(S2_LINE + b"\n", b"")), "the S2 line missing"
    assert page_problems(app + S2_LINE + b"\n"), "the S2 line twice"
    assert page_problems(app.replace(b'"api/reset', b'"/api/reset', 1)), "a slash left in"
    assert page_problems(app.replace(b"\n</body>", b"\n<!-- x --></body>", 1)), "a line added"


def test_a_changed_pin_hash_or_a_changed_app_file_is_caught(tmp_path):
    bad = json.loads(json.dumps(PIN))
    bad["source"]["files"]["j2_ui.html"]["sha256"] = "0" * 64
    assert page_problems((ASSETS / "j2_ui.html").read_bytes(), bad)
    root = tmp_path
    for rel in PIN["app"]["files"]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes((UI / rel).read_bytes())
    assert app_problems(root) == []
    (root / "j2ui_assets" / "j2_schema.py").write_bytes(b"x")
    assert app_problems(root) == ["j2ui_assets/j2_schema.py differs from the pin"]
    assert host_problems(b'fetch("/api/panel-token"); fetch("https://x.example/a"); fetch("/api/other")')


# ── layer 2: against the pinned commit's git objects ──────────────────────────────────────────────────────────────
def _sync():
    spec = importlib.util.spec_from_file_location("sync_j2_ui", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_j2_ui"] = mod
    spec.loader.exec_module(mod)
    return mod


def proto():
    """The prototype repo when it holds the pinned commit, else a skip with the reason (so the publish gate never needs
    a sibling checkout)."""
    path = os.environ["J2_PROTOTYPE"] if "J2_PROTOTYPE" in os.environ else PIN["source"]["path"]
    if not path or not (Path(path) / ".git").exists():
        pytest.skip("the prototype repo is not at %r (set J2_PROTOTYPE=<repo>); the hermetic checks above ran" % path)
    have = subprocess.run(["git", "-C", path, "cat-file", "-e", PIN["source"]["commit"] + "^{commit}"], capture_output=True)
    if have.returncode:
        pytest.skip("the prototype repo at %r does not hold the pinned commit %s" % (path, PIN["source"]["commit"][:7]))
    return path


def obj(repo, name):
    """The file as git holds it at the pinned commit; never the working tree (it may be dirty or have moved on)."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(["git", "-C", repo, "show", "%s:%s" % (PIN["source"]["commit"], name)], capture_output=True, check=True, env=env).stdout


def line_problems(orig, app, pin=PIN):
    """difflib over lines, independent of transform: equal, replace blocks that pair line for line (a line with S1 applied,
    or the one S3 href line), exactly one insert that is the S2 line, nothing deleted; the S1 total is the pin's."""
    s = subs(pin)
    a, b = orig.splitlines(keepends=True), app.splitlines(keepends=True)
    problems, total, inserted, s3 = [], 0, [], 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "delete":
            problems.append("lines %d-%d of the prototype's page are gone from the copy" % (i1 + 1, i2))
        elif tag == "insert":
            inserted += b[j1:j2]
        elif i2 - i1 != j2 - j1:
            problems.append("lines %d-%d changed in a way that does not pair line for line" % (i1 + 1, i2))
        else:
            for k, (old, new) in enumerate(zip(a[i1:i2], b[j1:j2])):
                want = S1.sub(rb"\1\2/", old)
                if new == want and new != old:
                    total += len(S1.findall(old))
                elif "S3" in s and new == want.replace(s["S3"]["original_href"].encode(), s["S3"]["new_href"].encode()) and new != want:
                    s3 += 1
                else:
                    problems.append("line %d is not the prototype's line with S1 applied: %r" % (i1 + k + 1, new[:80]))
    if [x.rstrip(b"\r\n") for x in inserted] != [S2_LINE]:
        problems.append("the one inserted line should be the S2 line, found %r" % inserted[:3])
    if total != s["S1"]["count"]:
        problems.append("S1 changed %d places, the pin says %d" % (total, s["S1"]["count"]))
    if ("S3" in s) != bool(s3):
        problems.append("the S3 href line: pin says %s, the lines say %d" % ("on" if "S3" in s else "off", s3))
    return problems


def test_pinned_commit_the_sync_scripts_transform_of_the_prototypes_page_is_the_copy_byte_for_byte():
    repo = proto()
    want, _ = _sync().transform(obj(repo, "j2_ui.html"), PIN["local_fonts"])
    got = (ASSETS / "j2_ui.html").read_bytes()
    if want != got:
        fail(["j2ui_assets/j2_ui.html is not transform(the prototype's page at %s)" % PIN["source"]["commit"][:7]])


def test_pinned_commit_an_independent_line_check_finds_only_the_documented_changes():
    repo = proto()
    problems = line_problems(obj(repo, "j2_ui.html"), (ASSETS / "j2_ui.html").read_bytes())
    if problems:
        fail(problems)


def test_pinned_commit_the_two_byte_copies_are_the_pinned_objects():
    repo = proto()
    assert (ASSETS / "j2_schema.py").read_bytes() == obj(repo, "j2_schema.py")
    assert (UI / "test_fixtures" / "j2ui" / "j2_ui_render.js").read_bytes() == obj(repo, "j2_ui_render.js")
    assert sha(obj(repo, "j2_ui.html")) == PIN["source"]["files"]["j2_ui.html"]["sha256"] == PAGE_SHA


def test_pinned_commit_the_line_check_catches_what_transform_alone_would_hide():
    repo = proto()
    orig, app = obj(repo, "j2_ui.html"), (ASSETS / "j2_ui.html").read_bytes()
    assert line_problems(orig, app) == []
    assert line_problems(orig, app.replace(b"J2 Department", b"J2 department", 1)), "one character"
    assert line_problems(orig, app.replace(S2_LINE + b"\n", b"")), "no S2 line"
    assert line_problems(orig, app.replace(b'"api/reset', b'"/api/reset', 1)), "a slash left in"
    assert line_problems(orig, b"".join(app.splitlines(keepends=True)[:-3])), "lines gone"
    wrong = json.loads(json.dumps(PIN))
    wrong["substitutions"][0]["count"] = 33
    assert line_problems(orig, app, wrong), "the pin's S1 total is checked"


def object_problems(repo, pin=PIN):
    """The pin's source hashes against the objects git holds at the pinned commit."""
    return ["%s: the pin's sha256 is not the prototype's object at %s" % (n, pin["source"]["commit"][:7])
            for n, want in pin["source"]["files"].items() if sha(obj(repo, n)) != want["sha256"]]


def test_pinned_commit_the_pins_hashes_are_the_objects_and_one_changed_byte_is_caught():
    repo = proto()
    assert object_problems(repo) == []
    bad = json.loads(json.dumps(PIN))
    h = bad["source"]["files"]["j2_ui.html"]["sha256"]
    bad["source"]["files"]["j2_ui.html"]["sha256"] = h[:-1] + ("0" if h[-1] != "0" else "1")
    assert object_problems(repo, bad) == ["j2_ui.html: the pin's sha256 is not the prototype's object at %s" % PIN["source"]["commit"][:7]]


# ── layer 3: a report, not a failure ──────────────────────────────────────────────────────────────────────────────
def test_the_prototype_having_moved_is_a_report_and_exits_0():
    repo = proto()
    env = dict(os.environ, J2_PROTOTYPE=repo)
    r = subprocess.run([sys.executable, str(SCRIPT), "--check-latest"], capture_output=True, env=env)
    assert r.returncode == 0 and (b"has not moved" in r.stdout or b"has moved" in r.stdout), r.stdout
