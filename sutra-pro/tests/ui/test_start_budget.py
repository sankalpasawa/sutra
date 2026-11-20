"""D257 (port edit E25, amends D251 and D252): a team page's Budget chip in dollars (API price). It shows the team's own budget once
GET /api/engine/settings?dept= answers, and sends nothing for it; a choice (half, double, a typed amount) is sent with the next request only
as `usd_budget`, then the chip shows the team default again. The page's own `sendText` and submit handler run in node with a stub `$`."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "sutra_app" / "ui" / "pages" / "j2_ui.html").read_text(encoding="utf-8")
SEND = re.search(r"async function sendText\(text, usdBudget\)\{.*?\n\}\n", PAGE, re.S).group(0)
E25 = PAGE[PAGE.index("// E25 (D257)"):PAGE.index("if (LCHIP) LCHIP.reset(); });") + len("if (LCHIP) LCHIP.reset(); });")]
needs_node = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def node(body: str, *, usd=20):
    js = ("const listeners = {}; const document = {addEventListener: (k, f) => { listeners[k] = f; }};\n"
          "const mk = () => ({value: '', disabled: false, innerHTML: '', on: {}, addEventListener(k, f){ this.on[k] = f; }, contains: () => true,\n"
          "  querySelector: () => null});\n"
          "const EL = {lbox: mk(), lsend: mk(), lform: mk(), lbudget: mk()}; const $ = id => EL[id];\n"
          "const SENT = []; let RTNEW = {id: '', keys: [], sent: false}; const GETS = [];\n"
          "const fetch = async (url, o) => { SENT.push([url, JSON.parse(o.body)]); return {}; };\n"
          f"const SutraCtx = {{dept: 'web', api: {{get: async (p, q) => {{ GETS.push([p, q]); return {{effective: {{usd_budget: {json.dumps(usd)}}}}}; }}}}}};\n"
          "const window = {BudgetChip: require(" + json.dumps(str(ROOT / "sutra_app" / "ui" / "static" / "js" / "budget_chip.js")) + ")};\n"
          "const BudgetChip = window.BudgetChip;\n"
          + SEND + "\n" + E25 + "\n"
          "const ready = async () => { listeners.DOMContentLoaded(); await new Promise(r => setTimeout(r, 0)); };\n"
          "const submit = async t => { EL.lbox.value = t; EL.lform.on.submit({preventDefault(){}}); await new Promise(r => setTimeout(r, 0)); };\n"
          "const click = async attrs => { EL.lbudget.on.click({target: {closest: () => ({dataset: attrs, classList: {contains: () => false}})}}); };\n"
          "(async () => {" + body + "})().catch(e => { console.error(e); process.exit(1); });")
    done = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_chip_holder_is_in_the_start_form_and_the_credit_field_is_gone():
    form = PAGE[PAGE.index('<form class="sbox" id="lform">'):PAGE.index("</form>", PAGE.index('id="lform"'))]
    assert '<span id="lbudget" style="font-size:13px"></span>' in form
    assert 'id="lbudget" name="budget"' not in PAGE and "work credits" not in form and "lbudget()" not in PAGE


@needs_node
def test_chip_shows_team_default():
    got = node("await ready(); console.log(JSON.stringify({gets: GETS, html: EL.lbudget.innerHTML}));")
    assert got["gets"] == [["/api/engine/settings", {"dept": "web"}]]
    text = re.sub(r"<[^>]+>", "", got["html"].split("</summary>")[0]).replace("&middot;", "·")
    assert re.sub(r"\s+", " ", text).strip() == "Budget: $20 API price (team default) · change"


@needs_node
def test_nothing_is_sent_for_the_team_default_and_a_pick_goes_with_one_request_only():
    got = node("await ready(); await submit('a cafe site'); await click({usd: '40'}); await submit('a bigger site'); await submit('more please');"
               "console.log(JSON.stringify({sent: SENT, html: EL.lbudget.innerHTML}));")
    assert got["sent"] == [["/api/say", {"text": "a cafe site"}], ["/api/say", {"text": "a bigger site", "usd_budget": 40}],
                           ["/api/say", {"text": "more please"}]]
    assert "(team default)" in got["html"]                                        # back to the default after the send


@needs_node
def test_without_the_settings_answer_there_is_no_chip_and_no_budget():
    got = node("await submit('a cafe site'); console.log(JSON.stringify({sent: SENT, html: EL.lbudget.innerHTML}));")
    assert got == {"sent": [["/api/say", {"text": "a cafe site"}]], "html": ""}


@needs_node
def test_send_text_carries_usd_budget_beside_a_run_template():
    got = node("RTNEW = {id: 'cafe-site', keys: ['W-1'], sent: false}; await sendText('use it', 12.5); console.log(JSON.stringify(SENT));")
    assert got == [["/api/say", {"text": "use it", "template": "cafe-site", "workflows": ["W-1"], "usd_budget": 12.5}]]


def test_only_the_start_form_sends_a_budget():
    calls = re.findall(r"sendText\(([^)]*)\)", PAGE)
    assert [c for c in calls if re.fullmatch(r"\w+, \w+", c)] == ["text, usdBudget", "t, b"], calls
