"""test_j2ui_xss.py -- hostile strings: nothing a record holds can become markup in the page
(UI port, package j2ui-verify, step T4).

The page runs in an iframe of the panel's own origin (it can read /api/panel-token and call every route of the app), and its own
esc() escapes & < > and " but not '. So the standing protection is a render test, not a reading of the code: seed a department in
which every string the adapter sends is an attacker's, render every pane of the page on it, and look for what an injection would
have made. The page is the prototype's, never edited: a breakout through one of the adapter's fields is the adapter's to mend; one
through the prototype's own template is reported (design/PRD-FIVE-FUNCTIONS-J2UI.md), and the adapter may then escape the one field.

Named claims:
  T4-1  the hostile department reaches the page: most of its 77 fields are in the adapter's answers and the greater part of them are
        printed in the panes, as text, payload and all (so the test below is not looking at an empty page)
  T4-2  in every pane (the fifteen of the spec and the rest, the Map, Documents, Artifacts, Board, the message dialog of every agent's
        message) there is no script, no on* attribute, no img that is not the page's own, no javascript: link, no unsandboxed frame and no
        raw </script>; the HTML parser finds only the page's own tags
  T4-3  the same when the payloads arrive through the owner's own mouth (POST api/say) and when the department has no goal
  T4-4  the check is not a rubber stamp: a copy of the page in a temp folder in which one field is printed raw (a goal, a message, a
        file name in a single-quoted attribute, which esc() does not protect) turns it red

Run: ./run-tests.sh test_j2ui_xss.py"""
import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

import app as app_module
from test_fixtures.j2ui import harness as H
from test_fixtures.j2ui import seed as SEED

UI = H.HERE.parents[1]
COPY = UI / "j2ui_assets" / "j2_ui.html"
DEPT_FIELDS = 78
#: fields the page prints as text; each must be in some pane, payload and all
MUST_SHOW = ("department name", "goal", "Identity message", "rule", "done-when item", "fact to confirm", "owner words", "Identity question", "Identity why",
             "options ask text", "options ask title", "option label", "option cost", "publish ask text", "finding ask text", "finding claim",
             "finding page", "board question", "board answer", "step answer", "step note", "conflict why", "why no", "why the plan",
             "workflow.validated message", "workflow.registered message", "workflow.blocked message", "clean reading", "Build check note")


@pytest.fixture(scope="module")
def client():
    return TestClient(app_module.app, base_url="http://127.0.0.1")


class Parse(HTMLParser):
    """Every tag with its attributes, and the text a person reads."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags, self.text = [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))

    handle_startendtag = handle_starttag

    def handle_data(self, data):
        self.text.append(data)


#: the attributes that take a URL (a title that starts with javascript: is only a title)
URL_ATTRS = {"href", "src", "action", "formaction", "xlink:href", "data", "poster", "srcset", "background", "ping"}


def parse(html):
    p = Parse()
    p.feed(html)
    p.close()
    return p


def breakouts(panes):
    """What an injection would have made in these panes' HTML: [(pane, why)]. The page's own markup is fine: an svg, an img of an
    artifact, a frame with sandbox=\"\"; nothing of the page's makes a script, an on* attribute or a javascript: link."""
    found = []
    for name, html in panes.items():
        if re.search(r"</script", html, re.I):
            found.append((name, "a raw </script>"))
        for tag, attrs in parse(html).tags:
            if tag == "script":
                found.append((name, "a <script>"))
            if tag in ("object", "embed", "link", "meta", "base", "form"):
                found.append((name, "a <%s>" % tag))
            if tag == "iframe" and dict(attrs).get("sandbox") is None:
                found.append((name, "an iframe with no sandbox"))
            if tag == "img" and not str(dict(attrs).get("src") or "").startswith("api/artifact"):
                found.append((name, "an img that is not an artifact: src=%r" % dict(attrs).get("src")))
            for attr, value in attrs:
                if attr.lower().startswith("on"):
                    found.append((name, "a %s attribute on <%s>" % (attr, tag)))
                if attr.lower() in URL_ATTRS and str(value or "").strip().lower().startswith(("javascript:", "data:text/html", "vbscript:")):
                    found.append((name, "a %s of %s on <%s>" % (attr, str(value)[:20], tag)))
                if attr.lower() == "srcdoc":
                    found.append((name, "a srcdoc on <%s>" % tag))
    return found


def shown_fields(panes, payloads):
    """The fields whose tag is in the text of some pane (the parser has decoded the entities, so this is what a person reads)."""
    text = " ".join(" ".join(parse(h).text) for h in panes.values())
    return {payloads[t][0] for t in payloads if (" " + t) in text and payloads[t][1] in text}


def render(client, ref, page=COPY):
    bundle = H.adapter_bundle(client, ref)
    bundle["open_details"] = True
    got = H.run_harness(page, bundle)
    return bundle, got


@pytest.fixture
def hostile(tmp_path, monkeypatch, client):
    ref, m = SEED.seed(tmp_path, "hostile", env=monkeypatch)
    return ref, m


# ---- T4-1 ------------------------------------------------------------------------------------------------------------------
def test_t41_the_hostile_department_reaches_the_page_as_text(client, hostile):
    ref, m = hostile
    assert len(m.payloads) == DEPT_FIELDS
    assert all(any(x in p for x in SEED.PAYLOADS) for _, p in m.payloads.values()), "every field holds an attack"
    whole = [f for f, p in m.payloads.values() if all(x in p for x in SEED.PAYLOADS)]
    assert len(whole) >= 60, "and most hold all three of the spec's payloads in a row (the interface limits an option's label to 120 characters)"
    bundle, got = render(client, ref)
    assert got["ok"], got["errors"]
    import json
    blob = json.dumps(bundle, ensure_ascii=False)
    surfaced = {t for t in m.payloads if (" " + t) in blob or ("_" + t) in blob}
    assert len(surfaced) >= 60, sorted(set(m.payloads) - surfaced)
    shown = shown_fields(got["panes"], m.payloads)
    assert set(MUST_SHOW) <= shown, sorted(set(MUST_SHOW) - shown)
    assert len(shown) >= 40, len(shown)
    assert len([k for k in got["panes"] if k.startswith("detail:")]) >= 10, "the message dialog of every agent's message was opened"
    kinds = {x for t in m.payloads if m.payloads[t][0] in shown for x in SEED.PAYLOADS + SEED.EXTRAS_OF_ATTACK if x in m.payloads[t][1]}
    assert kinds == set(SEED.PAYLOADS + SEED.EXTRAS_OF_ATTACK), "each payload kind reached a pane, whole"


# ---- T4-2 ------------------------------------------------------------------------------------------------------------------
def test_t42_no_pane_of_the_page_breaks_out_on_the_hostile_department(client, hostile):
    ref, m = hostile
    bundle, got = render(client, ref)
    assert got["ok"], got["errors"]
    assert {"smsgs", "pane-goal", "pane-workflows", "pane-conflicts", "pane-audit", "pane-charter", "pane-timeline", "lanes", "steps", "pane-map",
            "pane-artifacts", "pane-board", "msgs", "needs", "waiting", "renderMap", "renderBoard", "renderArtifacts"} <= set(got["panes"])
    assert breakouts(got["panes"]) == []


def test_t42_the_page_prints_its_own_svg_and_artifact_img_so_the_checker_allows_exactly_those(client, hostile):
    ref, m = hostile
    _, got = render(client, ref)
    tags = {tag for html in got["panes"].values() for tag, _ in parse(html).tags}
    assert "svg" in tags and "button" in tags, "the Map is drawn"
    assert breakouts({"x": '<img class="artimg" alt="a" src="api/artifact?name=a">'}) == []
    assert breakouts({"x": '<iframe class="artframe" sandbox="" title="a" src="api/artifact?name=a"></iframe>'}) == []
    for html in ('<img src=x onerror=window.__xss=1>', '<div onclick="x">', '<a href="javascript:window.__xss=1">x</a>', "<script>1</script>",
                 'text </script> text', '<svg onload=1>', '<iframe src="api/artifact?name=a"></iframe>', "<p title='' onmouseover='window.__xss=1'>x</p>"):
        assert breakouts({"x": html}), html


# ---- T4-3 ------------------------------------------------------------------------------------------------------------------
def test_t43_the_owners_own_words_come_back_as_text(client, hostile):
    ref, m = hostile
    words = list(SEED.PAYLOADS) + list(SEED.EXTRAS_OF_ATTACK) + ["".join(SEED.PAYLOADS)]
    for i, payload in enumerate(words):
        r = client.post("/j2ui/%s/api/say" % ref, json={"text": payload + " said%d" % i})
        assert r.status_code == 200, (payload, r.text)
    bundle, got = render(client, ref)
    assert got["ok"], got["errors"]
    said = [x for x in bundle["state"]["chat"] if x["who"] == "user" and " said" in x["text"]]
    assert len(said) == len(words)
    assert breakouts(got["panes"]) == []
    text = " ".join(" ".join(parse(h).text) for h in got["panes"].values())
    for i, payload in enumerate(words):
        assert payload + " said%d" % i in text, "the owner's words are shown as they were typed"


def test_t43_a_department_with_no_goal_and_the_start_screen_break_nothing(client, tmp_path, monkeypatch):
    ref, m = SEED.seed(tmp_path, "start", env=monkeypatch)
    _, got = render(client, ref)
    assert got["ok"] and breakouts(got["panes"]) == []


# ---- T4-4 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("what,old,new,field", [
    ("a goal printed raw", "<dd>${esc(g.statement)}</dd>", "<dd>${g.statement}</dd>", "goal"),
    ("a file name in a single-quoted attribute", 'data-art="${esc(r.file)}"', "data-art='${esc(r.file)}'", "Brief file name"),
])
def test_t44_a_field_printed_raw_turns_the_check_red(client, hostile, tmp_path, what, old, new, field):
    ref, m = hostile
    text = COPY.read_text(encoding="utf-8")
    assert text.count(old) == 1, what
    synthetic = tmp_path / "synthetic.html"
    synthetic.write_text(text.replace(old, new), encoding="utf-8")
    _, got = render(client, ref, page=synthetic)
    assert got["ok"], "the page still draws"
    found = breakouts(got["panes"])
    assert found, what + " was not caught"
    print(what, "->", found[:2])


def test_t44_a_message_printed_raw_turns_the_check_red(client, hostile, tmp_path):
    ref, m = hostile
    text = COPY.read_text(encoding="utf-8")
    old = "<small>Your website team</small>${esc(plain(m.text))}</div>`;"
    assert text.count(old) == 1
    synthetic = tmp_path / "synthetic.html"
    synthetic.write_text(text.replace(old, "<small>Your website team</small>${plain(m.text)}</div>`;"), encoding="utf-8")
    _, got = render(client, ref, page=synthetic)
    assert breakouts(got["panes"]), "a team message printed raw is caught"
    assert breakouts({k: v for k, v in got["panes"].items() if k == "smsgs"}), "and it is the Simple view's"
