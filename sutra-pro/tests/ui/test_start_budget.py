"""D251 (port edit E25): the start page's optional "Budget (work credits)" field. It holds 100 by default, a send carries it as `budget`
with the first message only (the route makes it the task setting J2_BUDGET), and a value that is not a whole number from 1 to 100000
stops the send with a message on the field. There is no cap field. The page's own `lbudget` and `sendText` run in node with a stub `$`."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = (Path(__file__).resolve().parents[2] / "sutra_app" / "ui" / "pages" / "j2_ui.html").read_text(encoding="utf-8")
LBUDGET = re.search(r"const lbudget = \(\) => \{.*?return \+v; \};", PAGE, re.S).group(0)
SEND = re.search(r"async function sendText\(text, budget\)\{.*?\n\}\n", PAGE, re.S).group(0)
needs_node = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def node(body: str):
    js = ("const EL = {value: '', msg: null, reported: false, setCustomValidity(m){ this.msg = m; }, reportValidity(){ this.reported = true; }};\n"
          "const $ = id => id === 'lbudget' ? EL : null; const SENT = []; let RTNEW = {id: '', keys: [], sent: false};\n"
          "const fetch = async (url, o) => { SENT.push([url, JSON.parse(o.body)]); return {}; };\n"
          + LBUDGET + "\n" + SEND + "\n(async () => {" + body + "})().catch(e => { console.error(e); process.exit(1); });")
    done = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_field_is_in_the_start_form_with_100_and_the_limits_and_no_cap_field():
    form = PAGE[PAGE.index('<form class="sbox" id="lform">'):PAGE.index("</form>", PAGE.index('id="lform"'))]
    assert 'Budget (work credits) <input id="lbudget" name="budget" type="number"' in form
    assert 'min="1" max="100000" step="1" value="100"' in form
    land = PAGE[PAGE.index('id="sland"'):PAGE.index('id="swork"')]
    assert "cap" not in land.lower()


@needs_node
@pytest.mark.parametrize("value, want", [("100", 100), (" 250 ", 250), ("1", 1), ("100000", 100000),
                                         ("", None), ("0", None), ("100001", None), ("12.5", None), ("-3", None), ("1e3", None), ("abc", None)])
def test_lbudget_takes_a_whole_number_from_1_to_100000_and_stops_anything_else(value, want):
    got = node(f"EL.value = {json.dumps(value)}; const b = lbudget(); console.log(JSON.stringify({{b, msg: EL.msg, reported: EL.reported}}));")
    assert got["b"] == want
    assert (got["msg"], got["reported"]) == (("", False) if want else ("Budget: a whole number of work credits from 1 to 100000", True))


@needs_node
def test_send_text_carries_the_budget_only_when_given_and_beside_a_run_template():
    got = node("await sendText('a cafe site', 100); await sendText('more please'); RTNEW = {id: 'cafe-site', keys: ['W-1'], sent: false};"
               "await sendText('use it', 40); console.log(JSON.stringify(SENT));")
    assert got == [["/api/say", {"text": "a cafe site", "budget": 100}], ["/api/say", {"text": "more please"}],
                   ["/api/say", {"text": "use it", "template": "cafe-site", "workflows": ["W-1"], "budget": 40}]]


def test_only_the_start_form_sends_a_budget():
    calls = re.findall(r"sendText\(([^)]*)\)", PAGE)
    assert [c for c in calls if re.fullmatch(r"\w+, \w+", c)] == ["text, budget", "t, b"], calls      # the definition and the start form's submit
