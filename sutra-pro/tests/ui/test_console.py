"""The owner console page and the HTML error pages (GAP-CONSOLE; gaps G11 and G12; UI-1's third page).

Offline tests run the real `create_app` (scripted connector, fake launcher, no model call). The one browser test (SUTRA_BROWSER=1, skipped by the
gate) loads `/console` in headless Chrome against a real server with seeded usage and Atom log rows.
"""
from __future__ import annotations

import ast
import base64
import contextlib
import hashlib
import json
import re
import threading
import time
import warnings
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sutra_app.config import Settings
from sutra_app.connectors.router import PICK_PURPOSES
from sutra_app.engine.capabilities.agents import LIVE_PURPOSES
from sutra_app.main import create_app
from sutra_app.orchestrator.testing.fake_engine import FakeLauncher
from sutra_app.orchestrator.testing.scripted import ScriptedConnector
from sutra_app.ui import PAGES_DIR, STATIC_DIR, BootContext, inline_script_hashes, mount_static
from sutra_app.ui import routes as ui_routes

TOKEN = "console-token-0123456789abcdef"
BASE = "http://127.0.0.1:8780"
HTML = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
JSON = {"Accept": "application/json"}
CONSOLE_FILE = PAGES_DIR / "console.html"


def make_app(tmp_path):
    settings = Settings.load({}, data_dir=tmp_path / "data", token=TOKEN, env_file=tmp_path / "none.env", engine="fake", offline=True, watch_ms=20)
    return create_app(settings, connector=ScriptedConnector(), launcher=FakeLauncher())


@pytest.fixture
def app(tmp_path):
    return make_app(tmp_path)


@pytest.fixture
def client(app):
    with TestClient(app, base_url=BASE, raise_server_exceptions=False) as found:
        yield found


def boot_block(html: str) -> dict:
    found = re.search(r'<script type="application/json" id="sutra-boot">(.*?)</script>', html, re.S)
    assert found, "no boot block"
    return json.loads(found.group(1))


# ============================================ the page =======================================================================

def test_console_is_served_with_the_boot_block_and_the_headers_of_the_other_pages(client):
    response = client.get("/console")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    boot = boot_block(response.text)
    assert boot["page"] == "console" and boot["token"] == TOKEN and boot["dept"] == "" and boot["version"] == client.app.state.services.version
    home = client.get("/")
    for name in ("cache-control", "x-content-type-options", "referrer-policy"):
        assert response.headers[name] == home.headers[name]
    assert response.headers["cache-control"] == "no-store"
    assert client.head("/console").status_code == 200 and client.post("/console").status_code == 405


def test_the_policy_of_console_names_its_one_inline_script_by_hash_and_allows_no_other(client):
    csp = client.get("/console").headers["content-security-policy"]
    source = CONSOLE_FILE.read_text(encoding="utf-8")
    hashes = inline_script_hashes(source)
    assert len(hashes) == 1                                                   # only the Appearance line is inline
    script = re.search(r"<script>(.*?)</script>", source, re.S).group(1)
    assert "'sha256-" + base64.b64encode(hashlib.sha256(script.encode()).digest()).decode() + "'" in csp
    assert "'unsafe-inline'" not in re.search(r"script-src[^;]*", csp).group(0)
    assert csp == client.get("/").headers["content-security-policy"].replace(
        re.search(r"script-src[^;]*", client.get("/").headers["content-security-policy"]).group(0), re.search(r"script-src[^;]*", csp).group(0))


def test_the_page_uses_no_cdn_and_every_file_it_names_is_served(client):
    source = CONSOLE_FILE.read_text(encoding="utf-8")
    assert not re.search(r"""(?:src|href)=["']https?://""", source)
    names = re.findall(r"""(?:src|href)=["'](/ui/[^"']+)""", source)
    assert names and {"/ui/css/sutra-console.css", "/ui/js/console_view.js", "/ui/js/sutra_ctx.js", "/ui/js/sutra_events.js", "/ui/js/fnode_view.js"} <= set(names)
    for name in names:
        assert client.get(name).status_code == 200, name
    order = [source.index(f'src="/ui/js/{n}"') for n in ("sutra_ctx.js", "sutra_events.js", "fnode_view.js", "console_view.js")]
    assert order == sorted(order)                                                                             # dependencies load first


def test_the_page_has_the_three_panels_inside_the_root_the_script_listens_on():
    source = CONSOLE_FILE.read_text(encoding="utf-8")
    root = re.search(r'<main[^>]*id="console-root".*?</main>', source, re.S).group(0)
    assert [m for m in re.findall(r'<section[^>]*id="(c-[a-z]+)"', root)] == ["c-usage", "c-log", "c-health"]
    assert 'id="cstate"' in source and 'href="/"' in source


def test_boot_accepts_the_console_page_without_a_team_and_refuses_one():
    BootContext(page="console", token=TOKEN, version="1")
    with pytest.raises(ValidationError, match="console page belongs to no department"):
        BootContext(page="console", token=TOKEN, version="1", dept="web")
    with pytest.raises(ValidationError):
        BootContext(page="admin", token=TOKEN, version="1")


def test_home_has_one_plain_link_to_the_console_in_the_rail():
    source = (PAGES_DIR / "home.html").read_text(encoding="utf-8")
    links = re.findall(r'<a[^>]*href="/console"[^>]*>.*?</a>', source, re.S)
    assert len(links) == 1 and "Usage and log" in links[0] and "data-pane" not in links[0]
    rail = re.search(r'<nav class="rail tabs" id="rail".*?</nav>', source, re.S).group(0)
    assert links[0] in rail and 'id="railteams"' not in links[0]


APP = Path(__file__).resolve().parents[2] / "sutra_app"
PURPOSE_WORD = re.compile(r"^[a-z_]{1,24}$")        # the ledger's rule for a purpose (connectors.usage.PURPOSE_PATTERN)


def purposes_the_app_writes() -> set[str]:
    """Every purpose word the app's code gives a model call, read from its sources: a `purpose="x"` argument, a `"purpose": "x"` entry of a context, an assignment to a
    variable called `purpose` (a conditional's every branch) and the second argument of the engine's `_ask_tag(fn, purpose)`. The grouping column of `usage.py` is no purpose."""
    def leaves(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        return leaves(node.body) + leaves(node.orelse) if isinstance(node, ast.IfExp) else []

    found: set[str] = set()
    for path in sorted(APP.rglob("*.py")):
        if path == APP / "orchestrator" / "usage.py" or "seed" in path.parts:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")                        # J2's own files hold an escape (a backslash-d in j2_check.py) that Python warns about on every parse
            tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "purpose":
                found.update(leaves(node.value))
            elif isinstance(node, ast.Dict):
                found.update(w for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and k.value == "purpose" for w in leaves(v))
            elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "purpose" for t in node.targets):
                found.update(leaves(node.value))
            elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "_ask_tag" and len(node.args) >= 2:
                found.update(leaves(node.args[1]))
    return {word for word in found if PURPOSE_WORD.match(word)}


def test_the_console_has_plain_words_for_every_purpose_the_app_writes():
    """D159: the table of usage by purpose names each purpose in the owner's words (`PURPOSE_WORDS` of console_view.js; any other word shows as itself, so nothing is hidden). A new
    purpose in the engine, the router or the orchestrator fails here until it has its words; a name for a purpose nobody writes any more is kept (older rows of the ledger hold it)."""
    source = (STATIC_DIR / "js" / "console_view.js").read_text(encoding="utf-8")
    named = set(re.findall(r'(\w+): "', re.search(r"const PURPOSE_WORDS = freeze\(\{(.*?)\}\);", source, re.S).group(1)))
    written = purposes_the_app_writes()
    assert {"agent_turn", "plan", "judge", "agent_chat", "chat_plan", "connector_test"} <= written                    # the scan sees the purposes of the engine, the chat agent, the answers and Settings
    assert set(PICK_PURPOSES) | set(LIVE_PURPOSES) <= written
    assert written <= named, f"purposes with no words in console_view.js (PURPOSE_WORDS): {sorted(written - named)}"


def test_the_js_and_css_of_the_console_are_in_the_static_folder():
    assert (STATIC_DIR / "js" / "console_view.js").is_file() and (STATIC_DIR / "css" / "sutra-console.css").is_file()
    css = (STATIC_DIR / "css" / "sutra-console.css").read_text(encoding="utf-8")
    assert not re.search(r"https?://|@import|url\(", css)                                                     # no web font, no external file


# ============================================ the HTML error pages ===========================================================

def test_an_unknown_path_is_an_html_page_for_a_browser_and_the_json_answer_for_everything_else(client):
    page = client.get("/no/such/page", headers=HTML)
    assert page.status_code == 404 and page.headers["content-type"].startswith("text/html")
    assert "Sutra Pro" in page.text and "Not found" in page.text and "<code>/no/such/page</code>" in page.text
    assert page.headers["cache-control"] == "no-store" and "script-src 'self'" in page.headers["content-security-policy"] and "<script" not in page.text
    assert 'href="/"' in page.text and ">Home<" in page.text
    for headers in (JSON, {}, {"Accept": "*/*"}):
        other = client.get("/no/such/page", headers=headers)
        assert other.status_code == 404 and other.headers["content-type"].startswith("application/json") and other.json() == {"detail": "Not Found"}


def test_the_page_shows_the_request_id_of_the_response_and_the_log_path(client):
    page = client.get("/no/such/page", headers=HTML)
    rid = page.headers["x-request-id"]
    assert re.fullmatch(r"[0-9a-f]{12}", rid) and f"<code>{rid}</code>" in page.text
    assert f"<code>{client.app.state.services.settings.log_path}</code>" in page.text
    assert client.get("/no/such/page", headers=HTML).headers["x-request-id"] not in page.text          # a new id each time


def test_what_came_from_the_url_is_escaped_and_cut(client):
    hostile = client.get("/%3Cscript%3Ealert(1)%3C/script%3E", headers=HTML)
    assert hostile.status_code == 404 and "<script>alert" not in hostile.text and "&lt;script&gt;" in hostile.text
    long = client.get("/" + "a" * 300, headers=HTML)
    assert "a" * 81 not in long.text and "...</code>" in long.text


def test_a_404_from_the_orchestrators_error_envelope_is_a_page_for_a_browser_and_stays_the_envelope_for_a_script(client):
    page = client.get("/api/atoms/not-there", headers=HTML)
    assert page.status_code == 404 and page.headers["content-type"].startswith("text/html")
    script = client.get("/api/atoms/not-there", headers=JSON)
    assert script.status_code == 404 and script.json()["error"]["code"] == "not_found"


def test_a_500_is_an_html_page_with_the_request_id_and_no_detail(app):
    @app.get("/boom")
    def boom():
        raise RuntimeError("secret-detail-from-inside")
    with TestClient(app, base_url=BASE, raise_server_exceptions=False) as client:
        page = client.get("/boom", headers=HTML)
        assert page.status_code == 500 and page.headers["content-type"].startswith("text/html")
        assert "Something went wrong" in page.text and f"<code>{page.headers['x-request-id']}</code>" in page.text
        assert "secret-detail-from-inside" not in page.text and "RuntimeError" not in page.text
        script = client.get("/boom", headers=JSON)
        assert script.status_code == 500 and script.json()["error"]["code"] == "internal"


def test_only_a_404_or_a_500_becomes_a_page(client):
    refused = client.get("/api/ops/diagnostics", headers=HTML)                  # 401 bad_token
    assert refused.status_code == 401 and refused.json()["error"]["code"] == "bad_token"
    invalid = client.get("/api/usage/summary", params={"by": "nope"}, headers=HTML)
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "validation"
    assert client.post("/console", headers=HTML).status_code == 405


def test_an_accept_header_must_start_with_text_html():
    def request(accept):
        return type("R", (), {"headers": {"accept": accept} if accept is not None else {}})()
    assert ui_routes.wants_html(request("text/html")) and ui_routes.wants_html(request("TEXT/HTML,application/xhtml+xml"))
    assert ui_routes.wants_html(request("  text/html;q=0.9"))
    assert not ui_routes.wants_html(request("application/json, text/html")) and not ui_routes.wants_html(request("*/*"))
    assert not ui_routes.wants_html(request("")) and not ui_routes.wants_html(request(None))


def test_the_error_pages_work_on_a_bare_app_with_no_services_and_install_once():
    bare = FastAPI()
    mount_static(bare, STATIC_DIR)
    handlers = dict(bare.exception_handlers)
    assert ui_routes.install_error_pages(bare) is False and bare.exception_handlers == handlers
    with TestClient(bare, raise_server_exceptions=False) as client:
        page = client.get("/nothing", headers=HTML)
        assert page.status_code == 404 and "not available" in page.text and "<code>-</code>" in page.text
        assert client.get("/nothing").json() == {"detail": "Not Found"}


def test_a_page_that_is_already_html_keeps_its_own_404(client):
    unknown_team = client.get("/d/nobody/", headers=HTML)
    assert unknown_team.status_code == 404 and "No team called" in unknown_team.text


# ============================================ the real page in Chrome ========================================================

def seed(services):
    conn = services.db.conn()
    now = int(time.time())
    for n in range(30):
        status = ("closed", "verify_failed", "abandoned", "refused")[n % 4]
        body = {"atom_id": f"a-seed-{n:02d}", "node_id": "web.audit" if n % 2 else "web.identity", "goal": f"goal number {n}", "status": status,
                "verify": {"template": "file-exists", "exit_code": 0} if n % 3 else None, "attempt": 1, "model": "sonnet", "touches": [], "reason": None}
        conn.execute("INSERT INTO atom_ledger(atom_id, node_id, status, body, ts) VALUES (?,?,?,?,?)",
                     (f"a-seed-{n:02d}", body["node_id"], status, json.dumps(body), now - (30 - n) * 60))
    detail = json.dumps({"usd_basis": "reported", "billing": "subscription"})
    # (provider, usd, purpose, seconds ago): the first three are the calls of the first test (a Claude total of $0.75 in the last 7 days); the rest are what the table by purpose
    # shows: a Codex call with no dollars, a word no list has, a summary 20 days ago (inside 30 days, outside 7) and a stub row (shown only when the toggle is on)
    calls = (("claude", 0.25, "agent_turn", 0), ("claude", 0.5, "judge", 60), ("codex", None, "agent_chat", 120), ("codex", None, "plan", 180), ("claude", None, "from_a_later_release", 240),
             ("claude", 0.1, "summary", 20 * 86400), ("stub", None, "chat_plan", 300))
    for n, (provider, usd, purpose, ago) in enumerate(calls):
        conn.execute("INSERT INTO usage_ledger(at, provider, model, purpose, fn, atom_id, usd, tokens_in, tokens_out, ok, how, call_ref, detail_json)"
                     " VALUES (?,?,?,?,?,?,?,?,?,1,'native',?,?)", (now - ago, provider, "m", purpose, "audit", f"a-seed-{n:02d}", usd, 100, 20, f"seed{n}", detail))


@pytest.fixture
def real_server(tmp_path):
    import uvicorn
    app = make_app(tmp_path)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on", timeout_graceful_shutdown=2))
    thread = threading.Thread(target=lambda: contextlib.suppress(SystemExit) and server.run(), daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        assert time.monotonic() < deadline and thread.is_alive(), "the server did not start"
        time.sleep(0.02)
    seed(app.state.services)
    yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    server.should_exit = True
    thread.join(15)


@pytest.mark.browser
def test_the_console_paints_its_three_panels_and_the_log_filters_and_opens_a_card(real_server, browser):
    browser.expect_failed("/api/atoms/a-seed", 404)                    # the seeded log rows have no atom behind them: the card falls back to the ledger row
    browser.goto(real_server + "/console")
    browser.wait_for("window.ConsolePage && ConsolePage.state().log.loaded === true && document.querySelectorAll('#c-health .cchk').length === 14")
    assert browser.count("#c-usage .ctile") == 3 and browser.count("#c-usage [data-act='period']") == 4
    assert browser.count("#c-log .lrow") == 25                                         # one page of 25 of the 30 rows, newest first
    assert browser.js("document.querySelector('#c-log .lrow button').textContent") == "30"
    assert "$0.75" in browser.text("#c-usage .ctiles")
    browser.js("(() => { const s = document.getElementById('f-state'); s.value = 'closed'; s.dispatchEvent(new Event('change', {bubbles: true})); })()")
    browser.wait_for("document.querySelectorAll('#c-log .lrow.st-closed').length === document.querySelectorAll('#c-log .lrow').length")
    browser.click("#c-log .lrow button")
    browser.wait_for("document.querySelector('#c-card').textContent.includes('goal number')")
    assert [e for e in browser.console_errors if "404" not in e] == []


@pytest.mark.browser
def test_the_console_draws_the_table_by_purpose_in_plain_words_and_it_follows_the_period_and_the_stub_toggle(real_server, browser):
    """D159: "Usage by purpose" sits in the Usage and cost panel under the table by team; each row is a purpose in the owner's words with its calls, dollars and tokens (a call
    with no price leaves its dollars blank, a word the page has no name for shows as itself), the dearest first; the period picker and the stub toggle change its rows."""
    browser.goto(real_server + "/console")
    browser.wait_for("window.ConsolePage && ConsolePage.state().usage !== null && document.querySelectorAll('#c-usage .cpurpose').length >= 5")
    table = "#c-usage table.cpurposes"
    assert browser.text(f"{table} caption") == "Usage by purpose"
    assert browser.js("Array.from(document.querySelectorAll('#c-usage table')).map(t => t.querySelector('caption').textContent)") == ["By team and function", "Usage by purpose", "Top ten atoms by cost"]
    rows = lambda: browser.js(f"Array.from(document.querySelectorAll('{table} tbody tr'), r => Array.from(r.children, c => c.textContent.trim()))")  # noqa: E731
    assert browser.js(f"Array.from(document.querySelectorAll('{table} thead th'), c => c.textContent)") == ["Purpose", "Calls", "USD", "Tokens in", "Tokens out"]
    assert rows() == [["Judging workflows", "1", "$0.50", "100", "20"], ["Agents at work", "1", "$0.25", "100", "20"], ["Questions to agents", "1", "", "100", "20"],
                      ["from_a_later_release", "1", "", "100", "20"], ["Planning workflows", "1", "", "100", "20"]]               # 7 days, stub rows left out; Codex's rows have no dollars
    assert browser.js(f"document.querySelector('{table} [data-purpose=judge] th').title") == "judge"                                # the ledger's word, for whoever matches the table to a row
    assert browser.js(f"document.querySelector('{table} [data-purpose=from_a_later_release] th').hasAttribute('title')") is False   # a word the page does not know is its own name
    browser.click("#c-usage [data-act='period'][data-period='30d']")                                                              # the period picker: the summary 20 days ago comes in
    browser.wait_for(f"!!document.querySelector('{table} [data-purpose=summary]')")
    assert [r[0] for r in rows()] == ["Judging workflows", "Agents at work", "Chat summaries", "Questions to agents", "from_a_later_release", "Planning workflows"]   # $0.50, 0.25, 0.10, then no dollars
    assert "chat_plan" not in browser.js(f"Array.from(document.querySelectorAll('{table} tr[data-purpose]'), r => r.dataset.purpose).join()")
    browser.click("#c-usage [data-act='stub']")                                                                                   # the stub toggle: the stub row's purpose comes in
    browser.wait_for(f"!!document.querySelector('{table} [data-purpose=chat_plan]')")
    assert browser.text(f"{table} [data-purpose=chat_plan] th") == "Chat with Sutra"
    browser.click("#c-usage [data-act='period'][data-period='7d']")
    browser.wait_for(f"!document.querySelector('{table} [data-purpose=summary]')")
    assert browser.count(f"{table} tbody tr") == 6                                                                                # back in 7 days: five purposes and the stub row's
    assert browser.console_errors == []


# The header's three links ("Usage and cost", "Atom log", "Health") are found by what they are (the nav's accessible name and their targets), not by a class: the chat's "new messages
# below" pill is a zero-height box of its own (`.cjump`, sutra-panel.css) and the nav had that class too, so it was drawn at no height and its links hung out of it.
HEADER_NAV = 'header.shead nav[aria-label="On this page"]'
HEADER_LINKS = [("Usage and cost", "#c-usage"), ("Atom log", "#c-log"), ("Health", "#c-health")]
HEADER_BOXES = r"""(() => {
  const head = document.querySelector("header.shead"), nav = head.querySelector('nav[aria-label="On this page"]');
  const box = el => { const r = el.getBoundingClientRect(); return {left: r.left, top: r.top, right: r.right, bottom: r.bottom}; };
  const within = (a, b) => a.left >= b.left - .5 && a.right <= b.right + .5 && a.top >= b.top - .5 && a.bottom <= b.bottom + .5;
  const h = box(head), n = box(nav), t = box(head.querySelector("#stitle")), first = box(nav.querySelector("a"));
  return {
    width: innerWidth, head: [h.left, h.top, h.right, h.bottom].map(Math.round), nav: [n.left, n.top, n.right, n.bottom].map(Math.round),
    navInHeader: within(n, h), sideways: document.documentElement.scrollWidth > innerWidth,
    middles: [Math.round((t.top + t.bottom) / 2), Math.round((first.top + first.bottom) / 2)],                          // the title's and the first link's, from the top
    links: Array.from(nav.querySelectorAll("a"), a => {
      const b = box(a), at = document.elementFromPoint((b.left + b.right) / 2, (b.top + b.bottom) / 2);
      return {text: a.textContent, href: a.getAttribute("href"), box: [b.left, b.top, b.right, b.bottom].map(Math.round), inNav: within(b, n), inHeader: within(b, h),
              reached: !!at && a.contains(at)};
    }),
  };
})()"""


@pytest.mark.browser
def test_the_headers_links_sit_inside_the_header_in_both_themes_and_take_their_clicks(real_server, browser):
    """At 480px and under the header wraps and its links drop to a row under the title. They were drawn on a box of no height (the chat's rule for the pill of new messages
    reached the nav through the one class name), so they hung 8px out of the header, over the panels' edge (320, 375 and 480px, light and dark); from 520px they sat 10px below the
    title's line. Now each link is inside the nav's box, the nav inside the header's, a click in the middle of a link reaches it, and a real click goes to its panel and stays on the console."""
    problems: list[tuple] = []
    for theme in ("light", "dark"):
        browser.set_theme(theme)
        for width in (320, 375, 480, 1280):
            browser.set_size(width, 812)
            browser.goto(real_server + "/console")
            browser.wait_for("window.ConsolePage && ConsolePage.state().log.loaded === true")
            seen = browser.js(HEADER_BOXES)
            if [(link["text"], link["href"]) for link in seen["links"]] != HEADER_LINKS:
                problems.append((theme, width, "the links are not the three of the header", seen["links"]))
                continue
            for link in seen["links"]:
                if not (link["inNav"] and link["inHeader"] and link["reached"]):
                    problems.append((theme, width, link["text"], "box", link["box"], "nav", seen["nav"], "header", seen["head"], "reached", link["reached"]))
            if not seen["navInHeader"] or seen["sideways"]:
                problems.append((theme, width, "nav in header", seen["navInHeader"], "sideways", seen["sideways"], seen["nav"], seen["head"]))
            if width == 1280 and abs(seen["middles"][0] - seen["middles"][1]) > 2:
                problems.append((theme, width, "the links are not on the title's line", seen["middles"]))        # one row: the nav is centred on it like the title
            for text, panel in HEADER_LINKS:
                browser.click(f'{HEADER_NAV} a[href="{panel}"]')                             # a real click in the middle of the link
                here = browser.js("location.pathname + location.hash")
                if here != "/console" + panel:
                    problems.append((theme, width, f"a click on {text} went to {here}"))
    assert problems == [], problems
    assert browser.console_errors == []
