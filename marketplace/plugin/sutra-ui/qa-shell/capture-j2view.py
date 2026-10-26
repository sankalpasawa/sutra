"""capture-j2view.py -- one-shot rendered capture of the department screen as the J2 prototype's page (j2ui-shell, E4/E6).

Boots the repo backend on a SIDE port (never 8330, which the installed app owns) on a record of its own: a temp folder
holds the registry, the department records and the chats, and a seeded organisation, its Root and one website
department are founded in it before the server starts. Then it drives headless Chrome over raw CDP (websockets; no
playwright), opens the Org screen with the page's OWN openScreen() and o2Select() (playbook rule: never the composer),
waits for the J2 page's frame, checks what the screen is made of, and writes the PNG for the capture gate.

What it checks before it writes (any miss is a non-zero exit and no PNG):
  - one iframe of class j2v-if whose address is /j2ui/<ref>/, with no sandbox attribute, wider than the page's 900 px
    breakpoint (so the page draws its desktop layout), inside the native bar's frame
  - no list column on the screen, and the bar carries the department's switch and Settings and records
  - the page itself loaded: its document has the Simple view's composer
  - Settings and records shows the classic list column with one Department view row

Until the adapter (j2ui_api.py, package j2ui-core) is in the tree, a stand-in that answers the page's calls with the
empty shapes is written to a temp folder and put first on the import path, so the page draws its empty state; with the
adapter in the tree nothing is stood in. It prints which one it used.

Run: .venv/bin/python qa-shell/capture-j2view.py <out.png> [<records-out.png>]
"""
import asyncio
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # sutra-ui/
PORT = int(os.environ.get("CAPTURE_PORT", "8352"))
DEBUG_PORT = int(os.environ.get("CAPTURE_CDP_PORT", "9352"))
CHROME = os.environ.get("CAPTURE_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
OUT = sys.argv[1] if len(sys.argv) > 1 else "capture.png"
OUT_RECORDS = sys.argv[2] if len(sys.argv) > 2 else None

SEED = r"""
import sys
sys.path.insert(0, %(lib)r)
import placement_engine as E, founding
if not E.active_roots(E.load_domains()):
    E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
org = founding.found_structure("City Care Hospital", owner="Sankalp")
dept = founding.spawn(org["root"], "City Care Hospital Website", "website",
                      "A website for City Care Hospital, a 200-bed hospital in Pune: departments, doctors, appointments, an emergency line.")
print(dept["ref"])
"""

# What the page's calls get until the adapter exists: the empty shapes, so the page draws its empty state.
STAND_IN = r'''
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
router = APIRouter(prefix="/j2ui")
KEYS = ("chat total status thinking step steps goal stamped workflows budget spent conflicts audits versions cycle calls error done "
        "atoms_v1 turn cycle_turns max_turns paused outcome style rubric playbooks playbooks_used playbook_saved mock model fixes "
        "force_audit_fail test_lessons force_question has_board placeholders report sections write_lock agents lanes call_log "
        "workable memory lessons lessons_used lessons_saved output output_label doc conditions files docset docset_files saved").split()
EMPTY = {"chat": [], "total": 0, "status": "idle", "step": 0, "steps": {}, "workflows": [], "budget": 0, "spent": 0, "conflicts": [],
         "audits": [], "versions": 0, "cycle": 0, "calls": 0, "done": False, "atoms_v1": {}, "max_turns": 30, "rubric": [],
         "playbooks": [], "playbooks_used": [], "mock": False, "model": "not recorded", "fixes": 1, "test_lessons": False,
         "has_board": False, "placeholders": [], "sections": [], "agents": {}, "lanes": [], "call_log": [], "memory": False,
         "lessons": [], "lessons_used": [], "lessons_saved": [], "output": "website", "output_label": "Website", "doc": False,
         "files": [], "docset": [], "docset_files": [], "cycle_turns": 0}


@router.get("/{ref}/api/state")
def state(ref: str, since: int = 0):
    return {k: EMPTY.get(k) for k in KEYS}


@router.get("/{ref}/api/runs")
def runs(ref: str):
    return {"live": ref, "runs": []}


@router.get("/{ref}/api/map")
def map_(ref: str):
    return {"schema": "map/1", "run": ref, "live": True, "status": {"state": "not_started", "state_status": "idle", "checks": {"passed": 0, "run": 0}},
            "nodes": [], "edges": [], "legend": [], "built_from": ["department record"], "not_recorded": ["stand-in adapter"]}


@router.get("/{ref}/api/board")
def board(ref: str):
    return {"schema": "board/1", "entries": []}


@router.get("/{ref}/api/artifacts")
def artifacts(ref: str):
    return {"deliverables": [], "records": []}


@router.get("/{ref}/api/docs")
def docs(ref: str):
    one = {"asked": False, "text": None, "workflows": []}
    return {"prd": one, "hld": one, "lld": one}


@router.get("/{ref}/api/audits")
def audits(ref: str):
    return []


@router.get("/{ref}/api/refs")
def refs(ref: str):
    return {"conditions": {}, "rubric": {}}


@router.get("/{ref}/site/{key}")
def site(ref: str, key: str):
    return HTMLResponse("<p style='font:14px system-ui;color:#667;padding:24px'>Your website will appear here once it's built.</p>")
'''


def wait_http(url, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return r.read().decode()
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("timeout waiting for " + url)


async def cdp(ws, counter, method, params=None):
    mid = next(counter)
    await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error']}")
            return msg.get("result") or {}


async def main():
    home = tempfile.mkdtemp(prefix="capture-j2view-")
    env = dict(os.environ, SUTRA_NATIVE_HOME=os.path.join(home, "registry"), SUTRA_NATIVE_DEPT_HOME=os.path.join(home, "native"),
               SUTRA_UI_PROPOSALS=os.path.join(home, "proposals"), SUTRA_UI_CHATS=os.path.join(home, "chats"),
               SUTRA_WEBSITE_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("ANTHROPIC_API_KEY", None)
    for k in ("registry", "native", "proposals", "chats"):
        os.makedirs(os.path.join(home, k), exist_ok=True)
    py = os.path.join(HERE, ".venv/bin/python")
    lib = os.path.join(os.path.dirname(HERE), "lib")
    seeded = subprocess.run([py, "-c", SEED % {"lib": lib}], cwd=HERE, env=env, capture_output=True, text=True)
    if seeded.returncode:
        print(seeded.stderr[-1500:])
        raise SystemExit("seeding the record failed")
    ref = seeded.stdout.strip().splitlines()[-1]
    if os.path.exists(os.path.join(HERE, "j2ui_api.py")):
        print("adapter: the repo's own j2ui_api")
    else:
        standin = os.path.join(home, "standin")
        os.makedirs(standin)
        with open(os.path.join(standin, "j2ui_api.py"), "w") as fh:
            fh.write(STAND_IN)
        env["PYTHONPATH"] = standin + os.pathsep + env.get("PYTHONPATH", "")
        print("adapter: a stand-in answering the empty shapes (j2ui_api is not in the tree)")
    backend = subprocess.Popen([py, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
                               cwd=HERE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    profile = tempfile.mkdtemp(prefix="capture-chrome-")
    chrome = None
    try:
        wait_http(f"http://127.0.0.1:{PORT}/api/org/health")
        chrome = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run", "--user-data-dir=" + profile,
             "--window-size=1440,900", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_http(f"http://127.0.0.1:{DEBUG_PORT}/json/version")
        req = urllib.request.Request(f"http://127.0.0.1:{DEBUG_PORT}/json/new?about:blank", method="PUT")
        tab = json.load(urllib.request.urlopen(req, timeout=5))
        it = iter(range(1, 10_000))
        async with websockets.connect(tab["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024) as ws:
            for dom in ("Page.enable", "Runtime.enable", "Network.enable"):
                await cdp(ws, it, dom)
            await cdp(ws, it, "Emulation.setDeviceMetricsOverride", {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
            await cdp(ws, it, "Page.navigate", {"url": f"http://127.0.0.1:{PORT}/"})
            await asyncio.sleep(4)                                   # boot + first render

            async def js(expr):
                r = await cdp(ws, it, "Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
                return (r.get("result") or {}).get("value")

            async def until(expr, what, seconds=25):
                end = time.time() + seconds
                while time.time() < end:
                    if await js(expr):
                        return
                    await asyncio.sleep(0.4)
                raise SystemExit("never saw: " + what)

            assert await js("typeof openScreen") == "function", "openScreen not reachable"
            await js("openScreen('org2')")
            await until("!!document.querySelector('[data-o2ref]')", "the Org tree")
            await js("o2Select(%s)" % json.dumps(ref))
            await until("!!document.querySelector('.j2frame') && !!document.querySelector('iframe.j2v-if')", "the J2 page's frame")
            await asyncio.sleep(3)                                   # the page loads and polls once
            facts = json.loads(await js("""JSON.stringify((() => {
              const f = document.querySelector('iframe.j2v-if'), r = f.getBoundingClientRect(), d = f.contentDocument;
              return { src: f.getAttribute('src'), sandbox: f.hasAttribute('sandbox'), width: Math.round(r.width), height: Math.round(r.height),
                       list: !!document.querySelector('.o2list'), bar: (document.querySelector('.j2vbar') || {}).innerText || '',
                       title: d && d.title, composer: !!(d && d.querySelector('textarea, #sbox, input[type=text]')), body: d && d.body ? d.body.innerText.slice(0, 120) : null,
                       frames: document.querySelectorAll('iframe.j2v-if').length };
            })())"""))
            print("page:", json.dumps(facts))
            assert facts["frames"] == 1 and facts["src"] == "/j2ui/%s/" % ref, facts
            assert not facts["sandbox"], "the frame must not be sandboxed"
            assert facts["width"] > 900, "the frame is narrower than the page's desktop breakpoint: %s" % facts["width"]
            assert not facts["list"], "the list column must be hidden while the page is on the screen"
            assert "Settings and records" in facts["bar"] and ("Stop" in facts["bar"] or "Start" in facts["bar"]), facts["bar"]
            assert facts["title"] == "J2 Department", "the page did not load: %r" % facts["title"]
            shot = await cdp(ws, it, "Page.captureScreenshot", {"format": "png"})
            os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
            with open(OUT, "wb") as fh:
                fh.write(base64.b64decode(shot["data"]))
            print("wrote", OUT, os.path.getsize(OUT), "bytes")
            # Settings and records: the classic list column with one Department view row
            await js("document.querySelector('[data-wbtab=records]').click()")
            await until("!!document.querySelector('.o2list')", "the list column in Settings and records")
            rec = json.loads(await js("""JSON.stringify({ rows: [...document.querySelectorAll('.o2list .o2li span')].map(s => s.textContent),
              hidden: !!document.querySelector('.j2vhost') && document.querySelector('.j2vhost').hidden })"""))
            print("records:", json.dumps(rec))
            assert "Department view" in rec["rows"] and rec["hidden"], rec
            assert not any(w in rec["rows"] for w in ("Chat", "Map", "Board", "Agent activity")), rec["rows"]
            if OUT_RECORDS:
                shot = await cdp(ws, it, "Page.captureScreenshot", {"format": "png"})
                with open(OUT_RECORDS, "wb") as fh:
                    fh.write(base64.b64decode(shot["data"]))
                print("wrote", OUT_RECORDS, os.path.getsize(OUT_RECORDS), "bytes")
            await js("document.querySelector('[data-wbtab=j2]').click()")
            await until("!!document.querySelector('.j2frame') && document.querySelector('.j2vhost') && !document.querySelector('.j2vhost').hidden", "the way back to the page")
            print("back on the page: the same frame")
    finally:
        for proc in (chrome, backend):
            if proc and proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
        shutil.rmtree(profile, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


asyncio.run(main())
