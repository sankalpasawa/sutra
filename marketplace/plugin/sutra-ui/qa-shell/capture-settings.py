"""capture-settings.py -- one-shot rendered capture of Settings > Updates.

Boots the repo backend on a SIDE port (never 8330 -- the installed app owns
it), drives headless Chrome over raw CDP (websockets; no playwright), opens
the Settings screen via the page's OWN openScreen() (playbook rule: never the
composer), runs a real checkUpdates(), and writes the PNG for the capture
gate. Playbook gotcha applied: Runtime + Network enabled on the CDP session,
else --headless=new throttles lazy work into a fake hang.

Run: .venv/bin/python qa-shell/capture-settings.py <out.png>
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
PORT = int(os.environ.get("CAPTURE_PORT", "8331"))
DEBUG_PORT = int(os.environ.get("CAPTURE_CDP_PORT", "9333"))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT = sys.argv[1] if len(sys.argv) > 1 else "capture.png"


def wait_http(url, timeout=30):
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
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    backend = subprocess.Popen(
        [os.path.join(HERE, ".venv/bin/python"), "-m", "uvicorn", "app:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=HERE, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    profile = tempfile.mkdtemp(prefix="capture-chrome-")
    chrome = None
    try:
        health = wait_http(f"http://127.0.0.1:{PORT}/api/org/health")
        assert "mece" in health, "backend health has no mece key"
        chrome = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={DEBUG_PORT}",
             "--no-first-run", "--user-data-dir=" + profile,
             "--window-size=1440,1000", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_http(f"http://127.0.0.1:{DEBUG_PORT}/json/version")
        req = urllib.request.Request(
            f"http://127.0.0.1:{DEBUG_PORT}/json/new?about:blank", method="PUT")
        tab = json.load(urllib.request.urlopen(req, timeout=5))
        ws_url = tab["webSocketDebuggerUrl"]

        it = iter(range(1, 10_000))
        async with websockets.connect(ws_url, max_size=64 * 1024 * 1024) as ws:
            for dom in ("Page.enable", "Runtime.enable", "Network.enable"):
                await cdp(ws, it, dom)
            await cdp(ws, it, "Emulation.setDeviceMetricsOverride",
                      {"width": 1440, "height": 1000, "deviceScaleFactor": 2, "mobile": False})
            await cdp(ws, it, "Page.navigate", {"url": f"http://127.0.0.1:{PORT}/"})
            await asyncio.sleep(4)                                   # boot + first render

            async def js(expr):
                r = await cdp(ws, it, "Runtime.evaluate",
                              {"expression": expr, "awaitPromise": True, "returnByValue": True})
                return (r.get("result") or {}).get("value")

            assert await js("typeof openScreen") == "function", "openScreen not reachable"
            await js("openScreen('settings')")
            await asyncio.sleep(1)
            await js("checkUpdates()")                               # real GET /api/updates
            await asyncio.sleep(5)                                   # GitHub round-trip
            state = await js("JSON.stringify({have: !!S.upd, err: S.updError,"
                             " managed: S.upd && S.upd.desktop && S.upd.desktop.managed})")
            print("panel state:", state)
            await js("document.querySelector('.chsec') && "
                     "document.querySelector('.chsec').scrollIntoView()")
            await asyncio.sleep(0.5)
            shot = await cdp(ws, it, "Page.captureScreenshot", {"format": "png"})
            os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
            with open(OUT, "wb") as fh:
                fh.write(base64.b64decode(shot["data"]))
            print("wrote", OUT, os.path.getsize(OUT), "bytes")
    finally:
        for proc in (chrome, backend):
            if proc and proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
        shutil.rmtree(profile, ignore_errors=True)


asyncio.run(main())
