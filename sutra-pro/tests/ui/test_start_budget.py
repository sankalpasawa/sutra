"""D423 (port edit E25, amends D251 and D252): a team page's Budget chip in dollars (API price). It shows the team's own budget once
GET /api/engine/settings?dept= answers, and sends nothing for it; a choice (half, double, a typed amount) is sent with the next request only
as `usd_budget`, then the chip (a pill, "$20 budget ▾", and its popover) shows the team default again. The page's own `sendText` and submit handler run in node with a stub `$`."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "sutra_app" / "ui" / "pages" / "j2_ui.html").read_text(encoding="utf-8")
SEND = re.search(r"async function sendText\(text, usdBudget\)\{.*?\n\}\n", PAGE, re.S).group(0)
E25 = PAGE[PAGE.index("// E25 (D423)"):PAGE.index("if (LCHIP) LCHIP.reset(); });") + len("if (LCHIP) LCHIP.reset(); });")]
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
    pill = re.search(r'<button type="button" class="bchippill"[^>]*>(.*?)</button>', got["html"])
    assert re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", pill.group(1)).replace("&#9662;", "▾")).strip() == "$20 budget ▾"
    assert 'aria-label="$20 budget, team default, API price"' in pill.group(0) and 'aria-expanded="false"' in pill.group(0)


@needs_node
def test_nothing_is_sent_for_the_team_default_and_a_pick_goes_with_one_request_only():
    got = node("await ready(); await submit('a cafe site'); await click({usd: '40'}); await submit('a bigger site'); await submit('more please');"
               "console.log(JSON.stringify({sent: SENT, html: EL.lbudget.innerHTML}));")
    assert got["sent"] == [["/api/say", {"text": "a cafe site"}], ["/api/say", {"text": "a bigger site", "usd_budget": 40}],
                           ["/api/say", {"text": "more please"}]]
    assert "$20 budget, team default" in got["html"]                              # back to the default after the send


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


# ---- E27 (D423): the team page's raise card takes a typed amount in dollars ---------------------------------------------------------
SRAISE = PAGE[PAGE.index("function sRaise(s, kind, live){"):PAGE.index("function sCardClick(e){")]
RAISE_CLICK = PAGE[PAGE.index("  if (b.dataset.raise !== undefined){"):PAGE.index('  const inp = c.querySelector(".own input");')]
PAUSED = {"kind": "limit", "questions": [{"question": "This run has used $20.40 of $20 (API price). Add $10? So far: $20 approved.",
                                          "options": ["Add $10 and keep going: more. Or type your own amount", "Finish as it is"], "budget": [10, 0]}]}


def raise_node(body: str):
    js = ("const window = {BudgetChip: require(" + json.dumps(str(ROOT / "sutra_app" / "ui" / "static" / "js" / "budget_chip.js")) + ")};\n"
          "const BudgetChip = window.BudgetChip; const SENT = []; const sendText = t => SENT.push(t);\n" + SRAISE + "\n"
          "function click(value){ const i = {value, attrs: {}, setAttribute(k, v){ this.attrs[k] = v; }}; const c = {querySelector: () => i};\n"
          "  const b = {dataset: {raise: ''}}; (function(){ " + RAISE_CLICK + " })(); return i.attrs; }\n"
          "(() => {" + body + "})();")
    done = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@needs_node
def test_raise_card_sends_typed_dollars():
    got = raise_node(f"const s = {{paused: {json.dumps(PAUSED)}}}; const html = sRaise(s, 'limit', true);"
                     "const marks = [click('$15'), click('12.5'), click('0.5'), click('abc')];"
                     "console.log(JSON.stringify({html, sent: SENT, marks}));")
    assert 'value="$10"' in got["html"] and "Add and keep going" in got["html"] and "API price" in got["html"]
    assert got["sent"] == ["Add $15 and keep going", "Add $12.5 and keep going"]
    assert got["marks"] == [{}, {}, {"aria-invalid": "true"}, {"aria-invalid": "true"}]


@needs_node
def test_the_raise_input_is_only_on_a_live_dollar_question():
    credits = {**PAUSED, "questions": [{**PAUSED["questions"][0], "options": ["Add 30 work credits and keep going", "Finish"], "budget": [30, 0]}]}
    got = raise_node(f"const p = {json.dumps(PAUSED)}; const c = {json.dumps(credits)};"
                     "console.log(JSON.stringify([sRaise({paused: p}, 'limit', false), sRaise({paused: p}, 'fact', true), sRaise({paused: c}, 'limit', true),"
                     "sRaise({paused: {...p, questions: [{...p.questions[0], budget: [0, 0]}]}}, 'limit', true)]));")
    assert got == ["", "", "", ""]


@needs_node
def test_the_ruling_card_takes_a_typed_amount_too():
    """R2-2: the ruling's dollar question (an approval card) shows the same raise input, its amount filled in."""
    ruling = {"kind": "ruling_budget", "questions": [{"question": "This run has used $0.15 of $0.64 (API price). Add $1,020 so Identity's ruling is "
                                                                  "funded in full? So far: $0.64 approved.",
                                                      "options": ["Add $1,020 so the ruling is funded in full: Loyalty card",
                                                                  "Go with Priority's final answer (REFUSE): nothing"], "budget": [1020, 0]}]}
    got = raise_node(f"const p = {json.dumps(ruling)}; console.log(JSON.stringify(sRaise({{paused: p}}, 'ruling_budget', true)));")
    assert 'value="$1,020"' in got and "Add and keep going" in got
    assert "sRaise(s, kind, live) + `<div class=\"acts\">" in PAGE      # on the approval card, above Approve / Not now
