"""harness.py -- the captured fixtures and the poll harness, for Python tests (UI port, package j2ui-verify).

    captured_runs()        the run ids under test_fixtures/j2ui/captured (plus 'idle')
    captured(run, name)    one captured answer (state, map, board, artifacts, docs, audits, refs, runs, preview) as parsed JSON
    bundle_of(run)         the bundle poll_harness.js takes for that run: the answers, and ?run=ID for a saved run
    run_harness(html, b)   poll_harness.js on a page (a path or the page's text) and a bundle: {ok, errors, panes, polls, posts}
    adapter_bundle(client, ref)   the bundle of a live adapter: what the page would fetch, through a TestClient
    s1(text)               the prototype's page text after substitution S1 (the slash of an API path dropped)
    visible(html)          the text a person reads in a pane's HTML (tags and attribute values removed)

The harness needs node; a test that uses it skips with a printed reason when node is not on the PATH.
"""
import gzip
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
CAPTURED = HERE / "captured"
HARNESS = HERE / "poll_harness.js"
NAMES = ("state", "map", "board", "artifacts", "docs", "audits", "refs", "runs", "preview")
#: the prototype's S1 (scripts/sync_j2_ui.py): a quote then a slash then api, site, file or shot loses that slash
S1 = re.compile(r'(["\'`])/(api|site|file|shot)/')


def captured_runs():
    return sorted(p.name for p in CAPTURED.iterdir() if p.is_dir()) if CAPTURED.is_dir() else []


def captured(run, name):
    path = CAPTURED / run / (name + ".json.gz")
    if not path.is_file():
        return None
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def bundle_of(run):
    b = {n: captured(run, n) for n in NAMES}
    b = {k: v for k, v in b.items() if v is not None}
    if run != "idle":
        b["search"] = "?run=" + run                      # a saved run is opened with ?run=ID, as the prototype's own page does
    return b


def s1(text):
    return S1.sub(r"\1\2/", text)


def visible(html):
    out = re.sub(r"<(script|style)\b.*?</\1>", " ", str(html), flags=re.S | re.I)
    out = re.sub(r"<[^>]*>", " ", out)
    return re.sub(r"&(?:amp|lt|gt|quot|#39);", " ", out)


def need_node():
    if shutil.which("node") is None:
        print("j2ui tests: node is not on the PATH")
        pytest.skip("node is not on the PATH")


def state_keys():
    """The 56 keys of api/state (j2ui_common.STATE_KEYS): what a state must carry to be one the page was written for."""
    import j2ui_common
    return list(j2ui_common.STATE_KEYS)


def run_harness(html, bundle, timeout=120, keys=True):
    """poll_harness.js on a page and a bundle. `html` is a Path/str of a file, or the page's text (when it holds a newline).
    The bundle's state must carry the 56 keys of api/state (keys=False to skip the check)."""
    need_node()
    if keys and "expect_keys" not in bundle:
        bundle = dict(bundle, expect_keys=state_keys())
    with tempfile.TemporaryDirectory(prefix="j2ui-harness-") as tmp:
        page = Path(tmp) / "page.html"
        if isinstance(html, Path) or "\n" not in str(html):
            page = Path(html)
        else:
            page.write_text(str(html), encoding="utf-8")
        data = Path(tmp) / "bundle.json"
        data.write_text(json.dumps(bundle), encoding="utf-8")
        got = subprocess.run(["node", str(HARNESS), str(page), str(data)], capture_output=True, timeout=timeout, check=False)
    if got.returncode != 0:
        raise AssertionError("poll_harness.js exited %s: %s" % (got.returncode, got.stderr.decode("utf-8", "replace")[-600:]))
    return json.loads(got.stdout.decode("utf-8"))


def adapter_bundle(client, ref, base=None):
    """What the page would fetch from a department, through a TestClient on the full app: state (whole chat), map, board,
    artifacts, docs, audits, refs, runs, preview. The page asks for each of these once; so does this."""
    base = base or "/j2ui/%s/" % ref
    out = {}
    for name, path in (("state", "api/state?since=0"), ("map", "api/map"), ("board", "api/board"), ("artifacts", "api/artifacts"),
                       ("docs", "api/docs"), ("audits", "api/audits"), ("refs", "api/refs"), ("runs", "api/runs"),
                       ("preview", "api/preview?atom=W-1.a1")):
        r = client.get(base + path)
        if r.status_code == 200:
            out[name] = r.json()
    return out
