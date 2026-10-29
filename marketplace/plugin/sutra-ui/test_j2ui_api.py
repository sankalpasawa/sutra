"""test_j2ui_api.py -- the routes the J2 page calls, under /j2ui/{ref}/ (j2ui_api.py; UI port step C5).

Named claims:
  C5-1  every route answers on a seeded department with the right content type; an unknown ref, a Root, a department of kind default
        and a department of the first build are 404 on every route; a body that is not JSON is an empty one
  C5-2  with every other package's module absent, or failing, or answering in a wrong shape, the endpoints answer the page's own
        empty shapes and api/state still has its 57 keys
  C5-3  every api/<name> the pinned page names has a route here; api/runs is {live, runs: []} and a run that is not the live one is 404
  C5-4  the website_api.SAFE headers are on every site, file, shot and api/artifact response, whoever built the body and whatever
        headers it sent; a name with '..', a root or a backslash never reaches the module that serves it
  C5-5  JSON is cleaned (no private key, no path of this machine) and sent no-store; since slices the chat; the three POSTs that mean
        nothing answer 409 and the department's files do not change
"""
import hashlib
import json
import os
import re
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_fixtures.j2ui import proto
from test_fixtures.j2ui.core_fixtures import *  # noqa: F401,F403

import j2ui_api as API
import j2ui_common as C
import website_api

OTHERS = ("j2ui_work", "j2ui_audit", "j2ui_map", "j2ui_board", "j2ui_artifacts", "j2ui_site")
JSON_GETS = ("api/state", "api/runs", "api/map", "api/board", "api/artifacts", "api/docs", "api/audits", "api/refs", "api/preview", "api/call")
SERVED = ("site/latest", "site/v1/index.html", "file/prd.md", "shot/1", "api/artifact?name=brief/v1/brief.md")
POSTS = ("api/say", "api/reset", "api/output", "api/playbooks/clear", "api/lessons/clear")


@pytest.fixture
def client(mods):
    app = FastAPI()
    app.include_router(API.router)
    return TestClient(app)


@pytest.fixture
def absent(monkeypatch):
    """The other packages' modules are not there: the router answers the empty shapes."""
    for name in OTHERS:
        monkeypatch.setitem(sys.modules, name, None)


def fake(monkeypatch, **mods):
    """Put modules of the other packages in place: fake(monkeypatch, j2ui_map={'build': fn}, ...); the rest stay absent."""
    for name in OTHERS:
        monkeypatch.setitem(sys.modules, name, types.SimpleNamespace(**mods[name]) if name in mods else None)


def url(path, ref=REF):
    return "/j2ui/%s/%s" % (ref, path)


# ---- C5-1: the routes ----------------------------------------------------------------------------------------------------------
def test_c51_every_json_route_answers_json_no_store(client, absent):
    for path in JSON_GETS:
        r = client.get(url(path))
        expect = 404 if path == "api/call" else 200
        assert r.status_code == expect, (path, r.status_code, r.text[:100])
        assert r.headers["content-type"].startswith("application/json") and r.headers["cache-control"] == "no-store", path
    assert client.get(url("api/call")).json() == {"error": "no such call"}


def test_c51_the_files_and_sites_answer_text_with_the_safe_headers_when_nothing_builds_them(client, absent):
    for path in SERVED:
        r = client.get(url(path))
        assert r.status_code == 404 and r.text == "not found" and r.headers["content-type"].startswith("text/plain"), path
        for k, v in website_api.SAFE.items():
            assert r.headers[k.lower()] == v, (path, k)


@pytest.mark.parametrize("what", ["unknown", "old"])
def test_c51_a_department_the_view_is_not_for_is_404_on_every_route(mods, client, monkeypatch, what):
    ref = {"unknown": "dref-nobody", "old": "dref-o"}[what]
    if what == "old":
        monkeypatch.setenv("SUTRA_ENGINE_RUNTIME", "1")
        mods.W.create(ref, "Other", None, kind="website")
    for path in JSON_GETS + SERVED:
        r = client.get(url(path, ref))
        assert r.status_code == 404, (path, r.status_code)
        if not path.startswith(("site", "file", "shot", "api/artifact")) or r.headers["content-type"].startswith("application/json"):
            assert r.json() == {"error": "no such department"}, path
    for path in POSTS:
        r = client.post(url(path, ref), json={"text": "hello"})
        assert r.status_code == 404 and r.json() == {"error": "no such department"}, path
    assert client.get("/j2ui/..%2Fx/api/state").status_code == 404 and client.get("/j2ui/%2E%2E/api/state").status_code == 404


def test_c51_a_post_body_that_is_not_json_is_empty(client, absent):
    r = client.post(url("api/say"), content=b"not json at all", headers={"content-type": "application/json"})
    assert (r.status_code, r.json()) == (400, {"error": "empty"})
    assert client.post(url("api/say"), json=["a", "list"]).json() == {"error": "empty"}
    assert client.post(url("api/say"), json={"text": "   "}).status_code == 400


# ---- C5-2: the empty shapes ----------------------------------------------------------------------------------------------------
def test_c52_with_every_module_absent_the_empty_shapes_stand(client, absent):
    assert client.get(url("api/map")).json() == C.EMPTY_MAP("the map is not built")
    assert client.get(url("api/board")).json() == C.EMPTY_BOARD()
    assert client.get(url("api/artifacts")).json() == C.EMPTY_ARTIFACTS()
    assert client.get(url("api/docs")).json() == C.EMPTY_DOCS()
    assert client.get(url("api/audits")).json() == []
    assert client.get(url("api/refs")).json() == C.EMPTY_REFS()
    assert client.get(url("api/preview?atom=W-1.a1")).json() == C.EMPTY_PREVIEW()
    s = client.get(url("api/state")).json()
    assert list(s) == list(C.STATE_KEYS) and all(s[k] == C.EMPTY_STATE[k] for k in C.WORK_KEYS)


def test_c52_a_module_that_fails_or_answers_in_a_wrong_shape_leaves_the_empty_shape(client, monkeypatch, mods):
    def boom(ctx, *a):
        raise RuntimeError("it broke")
    fake(monkeypatch, j2ui_map={"build": boom}, j2ui_board={"build": lambda ctx: ["not", "a", "dict"]}, j2ui_artifacts={"listing": lambda ctx: None},
         j2ui_work={"docs": boom, "preview": lambda ctx, a: "x", "call": boom}, j2ui_audit={"audits_condensed": lambda ctx: {"a": 1}, "refs": boom})
    assert client.get(url("api/map")).json() == C.EMPTY_MAP("the map is not built")
    assert client.get(url("api/board")).json() == C.EMPTY_BOARD() and client.get(url("api/artifacts")).json() == C.EMPTY_ARTIFACTS()
    assert client.get(url("api/docs")).json() == C.EMPTY_DOCS() and client.get(url("api/preview?atom=x")).json() == C.EMPTY_PREVIEW()
    assert client.get(url("api/audits")).json() == [] and client.get(url("api/refs")).json() == C.EMPTY_REFS()
    r = client.get(url("api/call?id=1"))
    assert (r.status_code, r.json()) == (404, {"error": "no such call"})
    assert any("j2ui_map.build: RuntimeError" in x for x in C.get_ctx(REF).reasons)


def test_c52_a_module_that_answers_is_heard(client, monkeypatch):
    fake(monkeypatch, j2ui_map={"build": lambda c: {"schema": "map/1", "nodes": [{"id": "person:requester"}], "edges": [], "legend": C.LEGEND}},
         j2ui_board={"build": lambda c: {"schema": "board/1", "entries": [{"id": "B-1"}]}},
         j2ui_artifacts={"listing": lambda c: {"deliverables": [{"name": "Build"}], "records": []}},
         j2ui_work={"docs": lambda c: C.EMPTY_DOCS(), "preview": lambda c, atom: {"anchor": atom, "html": "<p>x</p>"},
                    "call": lambda c, cid: {"id": cid, "prompt": "p"} if cid == 3 else None},
         j2ui_audit={"audits_condensed": lambda c: [{"stage": "x"}], "refs": lambda c: {"conditions": {"N1": "text"}, "rubric": {}}})
    assert client.get(url("api/map")).json()["nodes"] == [{"id": "person:requester"}]
    assert client.get(url("api/board")).json()["entries"] == [{"id": "B-1"}]
    assert client.get(url("api/artifacts")).json()["deliverables"] == [{"name": "Build"}]
    assert client.get(url("api/preview?atom=W-1.a1")).json() == {"anchor": "W-1.a1", "html": "<p>x</p>"}
    assert client.get(url("api/audits")).json() == [{"stage": "x"}] and client.get(url("api/refs")).json()["conditions"] == {"N1": "text"}
    assert client.get(url("api/call?id=3")).json() == {"id": 3, "prompt": "p"} and client.get(url("api/call?id=4")).status_code == 404
    assert client.get(url("api/call?id=zz")).status_code == 404 and client.get(url("api/call")).status_code == 404


# ---- C5-3: what the page names -----------------------------------------------------------------------------------------------------
def page_text():
    asset = os.path.join(os.path.dirname(os.path.abspath(__file__)), "j2ui_assets", "j2_ui.html")
    if os.path.exists(asset):
        return open(asset, encoding="utf-8").read()
    return proto.show("j2_ui.html").decode("utf-8")


def test_c53_every_endpoint_the_page_names_has_a_route(client):
    html = page_text()
    names = set(re.findall(r"""["'`]/?api/([a-z]+(?:/[a-z]+)?)""", html))
    assert {"state", "say", "map", "board", "artifacts", "artifact", "docs", "audits", "refs", "preview", "call", "runs", "reset", "output"} <= names
    routes = {r.path for r in API.router.routes}
    have = {p.split("/api/", 1)[1] for p in routes if "/api/" in p}
    assert names <= have, sorted(names - have)
    for prefix in ("site", "file", "shot"):
        assert re.search(r"""["'`]/?%s/""" % prefix, html) and any("/%s/" % prefix in p for p in routes), prefix


def test_c53_runs_lists_no_saved_run_and_another_run_is_404(client, absent, mods):
    assert client.get(url("api/runs")).json() == {"live": REF, "runs": []}
    cycle(mods, "running", 6)
    C.touch(REF)
    assert client.get(url("api/runs")).json() == {"live": "cycle-test", "runs": []}
    for q in ("", "?run=", "?run=cycle-test", "?run=" + REF, "?since=0&run=cycle-test"):
        assert client.get(url("api/state" + q)).status_code == 200, q
    r = client.get(url("api/state?run=j2-20261008-153402"))
    assert (r.status_code, r.json()) == (404, {"error": "no such run"})


def test_c53_a_since_that_is_not_a_number_is_400(client, absent):
    for q in ("abc", "1.5", "0x1", "--2"):
        r = client.get(url("api/state?since=" + q))
        assert (r.status_code, r.json()) == (400, {"error": "bad since"}), q
    assert client.get(url("api/state?since=-3")).status_code == 200 and client.get(url("api/state?since=")).status_code == 200


# ---- C5-4: what a model or an engine wrote ------------------------------------------------------------------------------------------
def test_c54_everything_served_carries_the_safe_headers_whatever_the_module_sent(client, monkeypatch):
    html = b"<!doctype html><script>fetch('/api/panel-token')</script>"
    loose = {"Content-Security-Policy": "default-src *", "X-Content-Type-Options": "sniff", "Cache-Control": "max-age=999", "X-Extra": "kept"}
    fake(monkeypatch,
         j2ui_site={"site": lambda c, key, path="": (200, html, "text/html", dict(loose)) if path else (302, b"", "text/plain", {"Location": key + "/index.html"}),
                    "file": lambda c, name: (200, b"# hi", "text/markdown", dict(loose)), "shot": lambda c, n: (200, b"png", "image/png", dict(loose))},
         j2ui_artifacts={"served": lambda c, name: (html, "text/html")})
    r = client.get(url("site/latest/index.html"))
    assert r.status_code == 200 and r.content == html and r.headers["x-extra"] == "kept"
    served = [r, client.get(url("file/prd.md")), client.get(url("shot/8")), client.get(url("api/artifact?name=build/v1/index.html")),
              client.get(url("site/latest"), follow_redirects=False)]
    assert [x.status_code for x in served] == [200, 200, 200, 200, 302] and served[-1].headers["location"] == "latest/index.html"
    for x in served:
        for k, v in website_api.SAFE.items():
            assert x.headers[k.lower()] == v, (x.url, k, x.headers.get(k.lower()))
    assert served[3].content == html and served[3].headers["content-type"].startswith("text/html")


def test_c54_a_name_that_climbs_out_never_reaches_the_module(client, monkeypatch):
    seen = []
    fake(monkeypatch,
         j2ui_site={"site": lambda c, key, path="": (seen.append(("site", key, path)), (200, b"x", "text/plain", {}))[1],
                    "file": lambda c, name: (seen.append(("file", name)), (200, b"x", "text/plain", {}))[1],
                    "shot": lambda c, n: (seen.append(("shot", n)), (200, b"x", "text/plain", {}))[1]},
         j2ui_artifacts={"served": lambda c, name: (seen.append(("artifact", name)), (b"x", "text/plain"))[1]})
    bad = ["../../etc/passwd", "/etc/passwd", "a/../../b", "..", "a\\b", "C:/x", "a\x00b", ""]
    for n in bad:
        r = client.get(url("api/artifact"), params={"name": n})
        assert r.status_code == 404 and r.text == "not found", n
    for n in ("..", "%2e%2e", "a%5Cb"):
        assert client.get(url("file/" + n)).status_code == 404
        assert client.get(url("shot/" + n)).status_code == 404
    for p in ("..%2fx", "a%2f..%2f..%2fb", "%2e%2e%2fx", "x%2f%2e%2e%2fy", "%2fetc%2fpasswd"):          # a client may collapse a literal '..' before it is sent
        assert client.get(url("site/v1/" + p)).status_code == 404, p
    assert not any(API._safe_name(n) for n in bad + ["../x", "a/../b", "x/..", "/x", "x\\y"])
    assert all(API._safe_name(n) for n in ("index.html", "brief/v1/brief.md", "assets/site.css", "8", "prd.md"))
    assert seen == [], seen
    assert client.get(url("api/artifact"), params={"name": "build/v1/index.html"}).status_code == 200 and seen == [("artifact", "build/v1/index.html")]
    assert client.get(url("site/v1/style.css")).status_code == 200 and seen[-1] == ("site", "v1", "style.css")


# ---- C5-5: cleaned, no-store, sliced, and the three that mean nothing ----------------------------------------------------------------
def test_c55_json_is_cleaned_on_the_way_out(client, monkeypatch, machine):
    machine("/Users/x")
    fake(monkeypatch, j2ui_board={"build": lambda c: {"schema": "board/1", "entries": [{"id": "B-1", "token": "t", "question": "see /Users/x/y/z.txt, due 5/6/2026",
                                                                                      "file": "build/v1/index.html"}]}})
    e = client.get(url("api/board")).json()["entries"][0]
    assert "token" not in e and e["question"] == "see z.txt, due 5/6/2026" and e["file"] == "build/v1/index.html"


def test_c55_the_owners_words_reach_the_page_as_they_were_said(mods, client, born, tick):
    """'/home', '/private', '/var' and '/opt-in' in the owner's words are pages of the owner's site, not paths of this machine."""
    ref = born()
    words = "Make /home the landing page and keep /private hidden; /opt-in and /root too, see /var and /tmp and /etc"
    assert client.post(url("api/say", ref), json={"text": words}).json() == {"ok": True}
    d = mods.W.dept(ref)
    d["goal"] = "A site whose /home is the landing page"
    d["rules"] = [{"id": "u-1", "tag": "refuse", "line": "never link /private from /home"}]
    d["done_items"] = [{"id": "D1", "text": "/opt-in works and /root redirects", "how": "code", "level": "target"}]
    mods.W.save_dept(ref, d)
    C.touch(ref)
    s = client.get(url("api/state", ref)).json()
    assert [m["text"] for m in s["chat"] if m["who"] == "user"][-1] == words
    assert s["goal"]["statement"] == "A site whose /home is the landing page" and s["goal"]["rules"] == ["never: never link /private from /home"]
    assert s["goal"]["done_when"] == ["/opt-in works and /root redirects"]


#: the owner's rule, quoted routes and all: pages of the site (a route that is not a path of this machine, and 'Plan B:/pricing')
ROUTES = "Never link /private/area from the menu, always keep /home/about first, and Plan B:/pricing stays; /private/members is for members"
AUDITED = "Never link /private/area from the menu and always keep /home/about first"        # a done-when the owner stamped, as Audit reads it


def test_c55_routes_the_owner_quoted_reach_the_page_unchanged_in_every_voice(mods, client, machine):
    """The verifier's finding N1. The owner says 'Never link /private/area from the menu and always keep /home/about first'; the
    stamp question Identity puts, Identity's and Adaptation's messages, the pause the page draws, and a condition all reach the
    page with the routes as they were said, so the owner stamps the rule that was recorded. ('clean' used to drop '/home' and
    '/private' from them: 'A rule, as understood: Never link area from the menu and always keep about first'.) So do the lanes, the
    Map and the Audit tab (the done-when Audit read item by item, its evidence, `workable` and the line that waits on a fact)."""
    machine("/Users/me")
    rule = "A rule, as understood (it never does this, from now on): " + ROUTES
    stamp_ask(mods, "rule", text=rule, tag="refuse", line=ROUTES, words="the owner's words, said")
    thread(mods, "Identity", "Adaptation", "request", "line", tid="x-i", words=ROUTES)
    thread(mods, "Adaptation", "Priority", "propose", "line", tid="x-p", words=ROUTES)
    mods.W.VERS.add(mods.W._abase(REF, "Build"), {"index.html": "<p>x</p>"}, [], "r-x", {"ok": True, "notes": [ROUTES]}, mods.W.now())
    C.touch(REF)
    s = client.get(url("api/state")).json()
    said = [m["text"] for m in s["chat"]]
    assert any(t.startswith("@Requester " + rule + "\n") for t in said), "\n".join(said)
    assert "Asked Adaptation for the plan: " + ROUTES in said and "Proposed the plan to Priority: " + ROUTES in said, said
    assert s["paused"]["questions"][0]["question"] == rule
    assert rule.startswith(s["paused"]["label"]) and "/private/area" in s["paused"]["label"], "the label is the question, cut to a line"
    assert [c["text"] for c in s["conditions"]] == [ROUTES]
    assert client.get(url("api/refs")).json()["conditions"] == {"N1": ROUTES}
    for route in ("/private/area", "/home/about", "Plan B:/pricing", "/private/members"):
        assert route in "\n".join(said), route
    # the lanes and the Map say the line Identity waits on the owner with: the question, cut to a line, routes as said (finding N1,
    # second part: functions_view scrubs its own read and used to make it 'Never link area from the menu ... keep about first')
    cut = rule[:139].rstrip() + "…"
    assert "/private/area" in cut and "/home/about" in cut
    lane = next(l for l in s["lanes"] if l["id"] == "identity")
    assert (lane["status"], lane["on"], lane["doing"]) == ("waiting", "you", cut)
    node = next(n for n in client.get(url("api/map")).json()["nodes"] if n["id"] == "fn:identity")
    assert (node["status"], node["detail"]) == ("waiting_on_you", cut)
    for text in (lane["doing"], node["detail"]):
        assert "link area from" not in text and "keep about first" not in text, text
    # the Audit tab (finding N1, third part): Audit's reading of the version, item by item, is read through its pane, which
    # functions_view scrubs; the done-when the owner stamped, Audit's evidence, `workable` and the line that waits on a fact are
    # made of it. None of the earlier asserts read state.audits, so none of them proved the Audit tab says the rule as recorded.
    cycle(mods, "running", 6)
    post(mods, "Audit", "Identity", "inform", {"word": "finding", "claim": AUDITED, "severity": "high", "about_version": 1,
                                               "findings": [{"page": "about.html", "claim": AUDITED, "severity": "high"}]},
         thread="x-find1", about={"art": "Live site", "v": 1})
    item = {"subject": "the menu", "severity": "high", "method": "code"}
    mods.R.audit_record(REF, None, "Live site", 1, True, None, [
        dict(item, id="D2", claim=AUDITED, verdict="not_met", evidence="the menu on /home/about links /private/area"),
        dict(item, id="D3", claim="Plan B:/pricing stays", verdict="to_confirm", evidence="nobody said whether /private/members is first")], [])
    C.touch(REF)
    s = client.get(url("api/state")).json()
    rows = {r["id"]: r for r in s["audits"][-1]["results"]}
    assert (rows["D2"]["criterion"], rows["D2"]["note"]) == (AUDITED, "the menu on /home/about links /private/area")
    assert rows["D3"]["needs_requester_fact"] == "Plan B:/pricing stays"
    assert rows["D3"]["note"] == "to confirm with you: nobody said whether /private/members is first"
    assert s["audits"][-1]["extra_issues"][0]["criterion"] == AUDITED, "the same tab says the one rule one way"
    assert s["workable"] == [AUDITED, "to confirm with you: Plan B:/pricing stays"]
    blob = json.dumps(s)
    assert "link area from" not in blob and "keep about first" not in blob and "Plan pricing" not in blob, "no voice of the page says it differently"


def test_c55_a_done_when_the_owner_is_asked_to_stamp_reads_the_same_on_the_pause_the_lane_and_the_map(mods, born, tick, client):
    """The verifier's end-to-end probe of finding N1 (second part): a Root sets a department up, the publish is stamped, then the
    owner says a rule and a done-when with quoted routes. The question they are asked to stamp, the Identity lane and the Map node
    all carry '/private/area' and '/home/about' as said; none of them says 'Never link area from the menu'."""
    ref = born()
    assert client.post(url("api/say", ref), json={"text": "Option 1"}).json() == {"ok": True}
    mods.W.run_until_idle(ref, limit=300)
    mods.R._unread_quiet(ref)                      # the version the stamp sent live was read, so no card for an unread one stands before the done-when
    said_by_owner = ("Never link /private/area from the menu and always keep /home/about first. Plan B:/pricing stays. "
                     "The done-when: /private/members is only for members")
    mods.W.owner_ask(born.root, said_by_owner, about=ref)
    mods.W.run_until_idle(born.root, limit=300)
    mods.W.run_until_idle(ref, limit=300)
    C.touch(ref)
    s = client.get(url("api/state", ref)).json()
    q = s["paused"]["questions"][0]["question"]
    assert q.startswith("Done when, as understood: add D2 Never link /private/area from the menu and always keep /home/about first."), q
    lane = next(l for l in s["lanes"] if l["id"] == "identity")
    node = next(n for n in client.get(url("api/map", ref)).json()["nodes"] if n["id"] == "fn:identity")
    for line in (lane["doing"], node["detail"]):
        assert line.startswith("Done when, as understood: add D2 Never link /private/area from the menu and always keep /home/about first."), line
        assert q.startswith(line.rstrip("…")), "the line is the question, cut to a line"
        assert "link area from" not in line and "keep about first" not in line, line


def test_c55_the_owners_own_words_in_an_ask_are_never_rewritten_even_under_this_machines_home(mods, client, machine):
    """An ask that ends with the owner's own words (an outside-the-site ask) says them as the owner said them, even a path under
    this machine's home; the lead the machine wrote passes the path rule."""
    machine("/Users/me")
    words = "keep /Users/me/site/index.html as it is, and /home/about too"
    ask(mods, "step", id="a-out", engine="Write", text="Write the page at /Users/me/work/out.txt: " + words, words=words)
    C.touch(REF)
    s = client.get(url("api/state")).json()
    q = s["paused"]["questions"][0]["question"]
    assert q == "Write the page at out.txt: " + words and s["paused"]["label"] == q
    assert [m["text"] for m in s["chat"] if m.get("act") == "ASK_REQUESTER"][0].startswith("@Requester Write the page at out.txt: " + words)
    lane = next(l for l in s["lanes"] if l["id"] == "identity")
    node = next(n for n in client.get(url("api/map")).json()["nodes"] if n["id"] == "fn:identity")
    assert lane["doing"] == q and node["detail"] == q, (lane["doing"], node["detail"])        # the lane and the Map say it as the pause does


def test_c55_since_slices_the_chat(mods, client, absent):
    for i in range(4):
        thread(mods, "Identity", "Adaptation", "request", "line", tid="x-%d" % i, words="w%d" % i)
    C.touch(REF)
    whole = client.get(url("api/state")).json()
    assert whole["total"] == 4 and [m["id"] for m in whole["chat"]] == [1, 2, 3, 4]
    part = client.get(url("api/state?since=3")).json()
    assert part["total"] == 4 and [m["id"] for m in part["chat"]] == [4]
    assert client.get(url("api/state?since=9")).json()["chat"] == [] and len(client.get(url("api/state")).json()["chat"]) == 4


def test_c55_say_and_the_three_that_mean_nothing(mods, client, absent, monkeypatch):
    ref = REF

    def h():
        d = hashlib.sha256()
        for root, dirs, files in os.walk(mods.home):
            dirs.sort()
            for f in sorted(files):
                d.update(open(os.path.join(root, f), "rb").read())
        return d.hexdigest()
    before = h()
    assert client.post(url("api/reset")).json() == {"ok": False} and client.post(url("api/reset")).status_code == 409
    r = client.post(url("api/output"), json={"type": "prd"})
    assert (r.status_code, r.json()) == (409, {"ok": False, "output": "website"})
    for p in ("api/playbooks/clear", "api/lessons/clear"):
        r = client.post(url(p))
        assert (r.status_code, r.json()) == (409, {"ok": False, "cleared": 0})
    assert h() == before
    asked = []
    monkeypatch.setattr(mods.W, "owner_ask", lambda *a, **k: asked.append((a, k)))
    r = client.post(url("api/say"), json={"text": "Add a page for visiting hours"})
    assert (r.status_code, r.json()) == (200, {"ok": True}) and asked == [((ref, "Add a page for visiting hours"), {})]


def test_c55_the_state_end_to_end_on_a_department_roots_set_up(mods, born, tick, client, absent):
    ref = born()
    r = client.get(url("api/state", ref))
    s = r.json()
    assert r.status_code == 200 and list(s) == list(C.STATE_KEYS) and s["total"] == len(s["chat"]) > 0
    assert s["paused"]["kind"] == "approval" and s["status"] == "waiting" and s["goal"]["site_name"]
    assert client.post(url("api/say", ref), json={"text": "Option 1"}).json() == {"ok": True}
    mods.W.run_until_idle(ref, limit=300)
    s2 = client.get(url("api/state?since=%d" % s["total"], ref)).json()
    assert s2["total"] > s["total"] and s2["chat"][0]["id"] == s["total"] + 1
    assert any(m["who"] == "user" and m["text"] == "Option 1" for m in s2["chat"])
    blob = str(s) + str(s2)
    for bad in ("GRANT", "COUNTER", "REFUSE", "accept-proposal", "reject-proposal", str(mods.home)):
        assert bad not in blob, bad


# ---- A5.1.2: the per-kind route matrix (the gate for the wording work) ---------------------------------------------------------------
KIND_ROUTES = ("api/state", "api/map", "api/board", "api/artifacts", "api/docs", "api/refs", "api/runs", "api/preview?atom=x", "api/audits")


def _seed(mods, kind):
    ref = "dref-k-" + kind
    mods.W.create(ref, "Kind %s" % kind, "A brief for the %s department" % kind if kind != "brief" else "Only a brief", kind="organic" if kind == "brief" else kind)
    return ref


@pytest.mark.parametrize("kind", ["website", "default", "organic", "root", "brief"])
def test_a512_every_kind_answers_every_read_route_with_200(mods, client, kind):
    ref = _seed(mods, kind)
    for path in KIND_ROUTES:
        r = client.get(url(path, ref))
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json"), (kind, path, r.status_code, r.text[:120])
    s = client.get(url("api/state", ref)).json()
    assert list(s) == list(C.STATE_KEYS)
    assert client.get(url("site/latest", ref)).status_code in (200, 404)
    for path in ("file/prd.md", "shot/1"):
        assert client.get(url(path, ref)).status_code == 404, (kind, path)
    r = client.post(url("api/say", ref), json={"text": "hello there"})
    assert r.status_code in (200, 202), (kind, r.status_code, r.text[:120])


def test_a512_a_kind_not_in_the_library_a_hostile_ref_and_a_runtime_1_record_are_404(mods, client, monkeypatch):
    ref = _seed(mods, "organic")
    f = mods.W.ddir(ref) / "dept.json"
    f.write_text(json.dumps(dict(json.loads(f.read_text()), kind="gone")))
    C.reset_caches()
    assert client.get(url("api/state", ref)).status_code == 404 and not C.is_j2_kind("gone")
    for bad in ("..%2Fx", "a%2Fb", "%2E%2E", "a b"):
        assert client.get("/j2ui/%s/api/state" % bad).status_code == 404, bad
    assert all(C.is_j2_kind(k) for k in mods.W.KINDS)


def test_a512_the_ctx_kind_is_the_records(mods):
    ref = _seed(mods, "default")
    assert C.get_ctx(ref).kind == "default"
    assert C.get_ctx(REF).kind == "website"


def _file(mods, ref, art, files):
    mods.W.add_version(ref, art, files, [], None, {"ok": True, "notes": ["ok"]})
    C.reset_caches()


def test_a512_state_says_the_kind_and_its_words_and_a_website_none(mods, client):
    s = client.get(url("api/state", REF)).json()
    assert (s["output"], s["output_label"], s["words"]) == ("website", "Website", {})
    for kind, label in (("default", "Result"), ("organic", "Work"), ("root", "Department")):
        ref = _seed(mods, kind)
        s = client.get(url("api/state", ref)).json()
        assert (s["output"], s["output_label"], s["doc"]) == (kind, label, False), kind
        assert s["words"]["team"] == "Kind %s" % kind and s["words"]["pick"] is False and s["words"]["examples"] == []


def test_a512_a_root_with_no_cycle_keeps_cycle_zero_and_is_never_faked(born, mods, client):
    born()
    root = born.root
    assert mods.W.dept(root)["kind"] == "root"
    s = client.get(url("api/state", root)).json()
    assert (s["cycle"], s["step"], s["stamped"], s["outcome"]) == (0, 0, False, None)
    assert s["output"] == "root" and list(s) == list(C.STATE_KEYS)
    for path in KIND_ROUTES:
        assert client.get(url(path, root)).status_code == 200, path


def test_a512_the_output_post_names_the_kind_and_changes_nothing(mods, client):
    ref = _seed(mods, "default")
    r = client.post(url("api/output", ref), json={"type": "prd"})
    assert (r.status_code, r.json()) == (409, {"ok": False, "output": "default"})
    r = client.post(url("api/output", REF), json={"type": "prd"})
    assert r.json() == {"ok": False, "output": "website"}


def test_a512_site_placeholder_and_text_page_per_kind(mods, client):
    web = client.get(url("site/latest", REF))
    assert "Your website will appear here" in web.text
    ref = _seed(mods, "default")
    r = client.get(url("site/latest", ref))
    assert r.status_code == 200 and "Nothing has been filed here yet." in r.text and "website" not in r.text
    art = mods.W.artifacts_of(mods.W.dept(ref))[-1]
    _file(mods, ref, art, {"notes.md": "# Notes <script>alert(1)</script>\nbody"})
    r = client.get(url("site/latest", ref))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "<pre" in r.text and "&lt;script&gt;" in r.text and "<script>" not in r.text
    for k, v in website_api.SAFE.items():
        assert r.headers[k.lower()] == v, k


def test_a512_the_map_says_j2_true_for_every_kind_and_false_for_the_old_build(mods, monkeypatch):
    import app as app_module
    c = TestClient(app_module.app, base_url="http://127.0.0.1")
    for kind in ("website", "default", "organic", "root"):
        ref = REF if kind == "website" else _seed(mods, kind)
        assert c.get("/api/native/%s/map" % ref).json()["j2"] is True, kind
    monkeypatch.setenv("SUTRA_ENGINE_RUNTIME", "1")
    mods.W.create("dref-old9", "Old", None, kind="website")
    assert c.get("/api/native/dref-old9/map").json()["j2"] is False


def test_a512_a_versionless_artifact_is_tagged_other_on_the_map(mods, client):
    ref = _seed(mods, "default")
    nodes = client.get(url("api/map", ref)).json()["nodes"]
    works = [n for n in nodes if n["kind"] == "work" and n["id"] != "work:charter"]
    assert works and all(n["tag"] != "Site" for n in works), [(n["label"], n["tag"]) for n in works]


@pytest.mark.parametrize("kind", ["default", "organic", "root"])
def test_a512_the_deliverable_per_kind_is_the_last_artifact_and_nothing_is_padded(mods, client, kind):
    ref = _seed(mods, kind)
    assert client.get(url("api/artifacts", ref)).json() == {"deliverables": [], "records": []}, "nothing filed, nothing listed"
    arts = mods.W.artifacts_of(mods.W.dept(ref))
    _file(mods, ref, arts[0], {"notes.md": "first"})
    listing = client.get(url("api/artifacts", ref)).json()
    names = [r["name"] for r in listing["deliverables"] + listing["records"]]
    assert names == [arts[0]], "one row for the one filed artifact, no filler"
    if len(arts) == 1:                                   # a kind with one artifact: it is the deliverable
        assert [r["name"] for r in listing["deliverables"]] == [arts[0]] and listing["records"] == []
        return
    assert listing["deliverables"] == [], "the deliverable is the last artifact, filed or not: a first draft is a record"
    _file(mods, ref, arts[-1], {"result.md": "last"})
    listing = client.get(url("api/artifacts", ref)).json()
    assert [r["name"] for r in listing["deliverables"]] == [arts[-1]] and [r["name"] for r in listing["records"]] == [arts[0]]
