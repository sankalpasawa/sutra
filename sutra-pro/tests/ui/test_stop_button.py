"""D254 (port edit E26): the team page's send button is Stop while the team's run is live. While the team works the box is disabled and
Stop stays pressable; while it waits for an answer it is Stop until the owner types, then Send again. Stop asks "Stop this run? What's
built so far is kept." and on yes calls the existing stop ladder once (POST /api/tasks/{id}/stop with {}, no force); 409 (already ended)
only refreshes. The page's own E26 code runs in node with a stub `$`, `confirm`, `SutraCtx.api`, `sToast` and `poll`."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = (Path(__file__).resolve().parents[2] / "sutra_app" / "ui" / "pages" / "j2_ui.html").read_text(encoding="utf-8")
E26 = PAGE[PAGE.index("// E26 (D254): Stop while"):PAGE.index('$("smsgs").addEventListener("click"')]
PAINT = re.search(r"const stop = sStopOn\(s\);[^\n]*?sStopMode\(stop\);", PAGE).group(0)
TASK = "tsk_a1b2c3d4e5f6"
needs_node = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def node(body: str, *, confirm="true", dept=None, post_error=None):
    dept = {"id": "web", "live_task_id": TASK} if dept is None else dept
    js = ("const mk = () => ({value: '', disabled: false, dataset: {}, attrs: {}, on: {}, setAttribute(k, v){ this.attrs[k] = v; },\n"
          "  addEventListener(k, f){ this.on[k] = f; }, querySelectorAll(){ return this.svgs || []; }});\n"
          "const EL = {sbox: mk(), ssend: mk(), sform: mk()};\n"
          "EL.ssend.svgs = [{dataset: {icon: 'send'}, style: {}}, {dataset: {icon: 'stop'}, style: {display: 'none'}}];\n"
          "const $ = id => EL[id]; let state = null; const LOG = []; const TOASTS = []; let POLLS = 0;\n"
          f"const confirm = q => {{ LOG.push(['confirm', q]); return {confirm}; }};\n"
          "const sToast = t => TOASTS.push(t); const poll = () => { POLLS += 1; }; const sendText = t => LOG.push(['send', t]);\n"
          f"const SutraCtx = {{dept: 'web', api: {{get: async p => {{ LOG.push(['GET', p]); return {json.dumps(dept)}; }},\n"
          f"  post: async (p, b) => {{ LOG.push(['POST', p, b]); const e = {json.dumps(post_error)}; if (e) throw e; return {{}}; }}}}}};\n"
          "const paint = (s, busy) => { " + PAINT + " };\n"
          "const view = () => ({stop: EL.ssend.dataset.stop === '1', label: EL.ssend.attrs['aria-label'], sendDisabled: EL.ssend.disabled, boxDisabled: EL.sbox.disabled,\n"
          "  icons: EL.ssend.svgs.filter(g => g.style.display !== 'none').map(g => g.dataset.icon)});\n"
          + E26 + "\n(async () => {" + body + "})().catch(e => { console.error(e); process.exit(1); });")
    done = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def submit():
    return "await EL.sform.on.submit({preventDefault(){}}); await new Promise(r => setTimeout(r, 0));"


def test_the_send_button_carries_a_hidden_stop_square_beside_the_arrow():
    form = PAGE[PAGE.index('<form class="scbox" id="sform">'):PAGE.index("</form>", PAGE.index('id="sform"'))]
    assert '<svg data-icon="send"' in form and '<svg data-icon="stop"' in form
    stop = form.split('<svg data-icon="stop"')[1].split("</svg>")[0]
    assert 'style="display:none"' in stop and "<rect" in stop


@needs_node
def test_stop_shows_while_live_and_box_empty():
    got = node("const s = {status: 'waiting', paused: {msg: 3}}; paint(s, false); console.log(JSON.stringify(view()));")
    assert got == {"stop": True, "label": "Stop the run", "sendDisabled": False, "boxDisabled": False, "icons": ["stop"]}


@needs_node
def test_stop_is_enabled_while_the_team_works_and_the_box_is_disabled():
    got = node("paint({status: 'running'}, true); console.log(JSON.stringify(view()));")
    assert got == {"stop": True, "label": "Stop the run", "sendDisabled": False, "boxDisabled": True, "icons": ["stop"]}


@needs_node
def test_typing_turns_stop_into_send_when_paused():
    got = node("state = {status: 'waiting', paused: {msg: 3}}; paint(state, false); EL.sbox.value = 'blue please'; EL.sbox.on.input();"
               "const a = view(); EL.sbox.value = ''; EL.sbox.on.input(); console.log(JSON.stringify([a, view()]));")
    assert got[0] == {"stop": False, "label": "Send", "sendDisabled": False, "boxDisabled": False, "icons": ["send"]}
    assert got[1]["stop"] is True


@needs_node
@pytest.mark.parametrize("s", [{"status": "done"}, {"status": "waiting", "paused": {"msg": 3}, "saved": "run-1"}, {"status": "running", "saved": "run-1"}])
def test_send_not_stop_when_the_run_is_over_or_a_saved_run_is_shown(s):
    busy = s["status"] == "running" or bool(s.get("saved"))
    got = node(f"paint({json.dumps(s)}, {json.dumps(busy)}); console.log(JSON.stringify(view()));")
    assert got["stop"] is False and got["label"] == "Send" and got["icons"] == ["send"] and got["sendDisabled"] is busy


@needs_node
def test_confirm_then_one_post_without_force():
    got = node("paint({status: 'running'}, true);" + submit() + "console.log(JSON.stringify({LOG, TOASTS, POLLS}));")
    assert got["LOG"] == [["confirm", "Stop this run? What's built so far is kept."], ["GET", "/api/departments/web"],
                          ["POST", f"/api/tasks/{TASK}/stop", {}]]
    assert got["TOASTS"] == [] and got["POLLS"] == 1


@needs_node
def test_cancel_sends_nothing():
    got = node("paint({status: 'running'}, true);" + submit() + "console.log(JSON.stringify({LOG, POLLS}));", confirm="false")
    assert got == {"LOG": [["confirm", "Stop this run? What's built so far is kept."]], "POLLS": 0}


@needs_node
def test_409_refreshes_quietly():
    got = node("paint({status: 'running'}, true);" + submit() + "console.log(JSON.stringify({TOASTS, POLLS}));", post_error={"status": 409, "code": "busy"})
    assert got == {"TOASTS": [], "POLLS": 1}


@needs_node
def test_another_error_says_try_again():
    got = node("paint({status: 'running'}, true);" + submit() + "console.log(JSON.stringify({TOASTS, POLLS}));", post_error={"status": 0, "code": "network"})
    assert got == {"TOASTS": ["Could not stop the run. Try again."], "POLLS": 0}


@needs_node
def test_a_bad_or_missing_task_id_is_never_posted():
    got = node("paint({status: 'running'}, true);" + submit() + "console.log(JSON.stringify({LOG, POLLS}));", dept={"id": "web", "live_task_id": "../x"})
    assert [e[0] for e in got["LOG"]] == ["confirm", "GET"] and got["POLLS"] == 1


@needs_node
def test_send_mode_still_sends_the_typed_text():
    got = node("state = {status: 'waiting', paused: {msg: 3}}; paint(state, false); EL.sbox.value = 'blue please'; EL.sbox.on.input();"
               + submit() + "console.log(JSON.stringify(LOG));")
    assert got == [["send", "blue please"]]
