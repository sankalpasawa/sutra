"""test_j2ui_common.py -- the J2 view's scope, its cache, its journal tails and its empty shapes (j2ui_common.py; UI port step C1).

Named claims:
  C1-1  the state has exactly the prototype's 56 keys (the literal list, the prototype's own snapshot when it is here, the captured
        state when verify committed one), and EMPTY_STATE has exactly them
  C1-2  need() is the one scope: an unknown ref, a ref with path characters, a runtime-1 department, a Root and the kinds
        default and organic are all NotJ2; a runtime-2 website department is not
  C1-3  one read per signature: a second get_ctx with no file change reads nothing; a change rebuilds only after MIN_REBUILD_S
        unless touch(ref) was called
  C1-4  JournalTail reads 5,000 rows once and then only the row appended later, survives a torn last line, and re-reads after
        a truncation; the ledger is read from its last seq
  C1-5  caches are keyed by (home, ref): two homes in one process that reuse a ref never see each other
  C1-6  clean() leaves build/v1/index.html and 5/6/2026 alone, shortens a path of THIS machine (under its home, the records' home,
        the temp folder or the app's folder, ~/..., a Windows drive path) to its file name and drops a private key; a root with
        nothing under it ('/home', '/private', '/opt-in', '/root') and a route that is not under one of this machine's folders
        ('/home/about', '/private/members', 'Plan B:/pricing') are pages of the owner's site and reach the page as they were said;
        the owner's own words (a user message's text, the goal, a Said line) are never rewritten; the line a function waits on
        the owner with (the Identity lane, the Map node) is made from the ask, not from functions_view's own scrubbed one;
        functions_view scrubs its read with this same rule (machine_paths), so the Audit tab, the lanes and the Map, which are
        made of its read, say the owner's routes as the owner said them, and the two scrubs can never disagree
  C1-7  a department with no cycle is 'not_started'; a broken sub-read leaves its attribute empty, says why, and still gives a ctx
  C1-8  the W-k numbering, who/dest/fn_id and step_at, on a department Root set up
"""
import ast
import json
import os
from pathlib import Path

import pytest

from test_fixtures.j2ui import harness as H
from test_fixtures.j2ui import proto
from test_fixtures.j2ui.core_fixtures import *  # noqa: F401,F403

import functions_view as FV
import j2ui_common as C
import machine_paths as MP

KEYS56 = ["chat", "total", "status", "thinking", "step", "steps", "goal", "stamped", "workflows", "budget", "spent", "conflicts",
          "audits", "versions", "cycle", "calls", "error", "done", "atoms_v1", "turn", "cycle_turns", "max_turns", "paused",
          "outcome", "style", "rubric", "playbooks", "playbooks_used", "playbook_saved", "mock", "model", "fixes",
          "force_audit_fail", "test_lessons", "force_question", "has_board", "placeholders", "report", "sections", "write_lock",
          "agents", "lanes", "call_log", "workable", "memory", "lessons", "lessons_used", "lessons_saved", "output",
          "output_label", "doc", "conditions", "files", "docset", "docset_files", "saved"]
UI = Path(__file__).resolve().parent


def spy(monkeypatch, obj, name):
    real, calls = getattr(obj, name), []

    def wrapped(*a, **k):
        calls.append(a)
        return real(*a, **k)
    monkeypatch.setattr(obj, name, wrapped)
    return calls


# ---- C1-1: the shapes -------------------------------------------------------------------------------------------------
def test_c11_the_state_has_the_prototypes_56_keys():
    assert list(C.STATE_KEYS) == KEYS56 and len(set(KEYS56)) == 56
    assert list(C.EMPTY_STATE()) == KEYS56
    # the work package's thirteen are among them
    assert set(C.WORK_KEYS) <= set(KEYS56) and len(C.WORK_KEYS) == 13
    # a fresh copy each call: nobody shares the lists
    a, b = C.EMPTY_STATE(), C.EMPTY_STATE()
    a["chat"].append(1)
    assert b["chat"] == [] and C.EMPTY_STATE["chat"] == []


def test_c11_the_keys_are_the_prototypes_own_snapshot():
    """J2Run.snapshot (48 keys) + output_info (7 more) + saved (j2_server), read from the pinned j2.py without running it."""
    tree = ast.parse(proto.show("j2.py").decode("utf-8"))
    snap = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "snapshot")
    keys = next([k.value for k in r.value.keys if isinstance(k, ast.Constant)]
                for r in ast.walk(snap) if isinstance(r, ast.Return) and isinstance(r.value, ast.Dict))
    info = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "output_info")
    more = next([k.value for k in r.value.keys] for r in ast.walk(info) if isinstance(r, ast.Return))
    assert list(dict.fromkeys(keys + more + ["saved"])) == KEYS56


def test_c11_the_captured_state_when_there_is_one():
    """The prototype's own states, captured by j2ui-verify (captured/<run>/state.json.gz, read through the harness): each has
    exactly STATE_KEYS. The order is not asserted: j2_server puts 'saved' first in a saved run, and the page reads by name."""
    runs = [r for r in H.captured_runs() if H.captured(r, "state") is not None]
    if not runs:
        pytest.skip("test_fixtures/j2ui/captured holds no captured state yet (j2ui-verify T1)")
    for run in runs:
        st = H.captured(run, "state")
        assert isinstance(st, dict) and len(st) == 56, (run, len(st))
        assert set(st) == set(KEYS56) == set(C.STATE_KEYS), (run, sorted(set(st) ^ set(KEYS56)))


def test_c11_the_other_empty_shapes_are_the_prototypes():
    assert C.EMPTY_BOARD == {"schema": "board/1", "entries": []} and C.EMPTY_BOARD() is not C.EMPTY_BOARD
    assert C.EMPTY_ARTIFACTS() == {"deliverables": [], "records": []}
    assert C.EMPTY_DOCS() == {k: {"asked": False, "text": None, "workflows": []} for k in ("prd", "hld", "lld")}
    assert C.EMPTY_REFS() == {"conditions": {}, "rubric": {}} and C.EMPTY_PREVIEW() == {"anchor": None, "html": None}
    m = C.EMPTY_MAP("why not")
    assert list(m) == ["schema", "run", "live", "status", "nodes", "edges", "legend", "built_from", "not_recorded"]
    assert m["schema"] == "map/1" and m["not_recorded"] == ["why not"] and len(m["legend"]) == 14


def test_c11_the_legend_is_the_prototypes():
    if proto.skip_reason():
        pytest.skip(proto.skip_reason())
    assert C.LEGEND == proto.consts("j2_map.py", "LEGEND") and C.EMPTY_MAP()["legend"] == C.LEGEND


# ---- C1-2: the scope --------------------------------------------------------------------------------------------------
def test_c12_need_is_the_one_scope(mods, monkeypatch):
    W = mods.W
    assert C.need(REF)["ref"] == REF and C.is_j2_kind("website") and not C.is_j2_kind("default")
    for bad in ("dref-nobody", "../x", "a/b", "..", ".", "", "x" * 200, None, 7):
        with pytest.raises(C.NotJ2):
            C.need(bad)
    W.create("dref-root", "Acme", None, kind="root")
    W.create("dref-def", "Defaulted", None, kind="default")
    W.create("dref-org", "Organic", None, kind="organic")
    for ref in ("dref-root", "dref-def", "dref-org"):
        assert W.dept(ref)["runtime"] == 2
        with pytest.raises(C.NotJ2):
            C.need(ref)
    monkeypatch.setenv("SUTRA_ENGINE_RUNTIME", "1")
    W.create("dref-old", "Old way", None, kind="website")
    assert W.dept("dref-old")["runtime"] == 1
    with pytest.raises(C.NotJ2):
        C.need("dref-old")


# ---- C1-3: one read per signature -------------------------------------------------------------------------------------
def test_c13_a_second_read_with_no_change_reads_nothing(mods, monkeypatch):
    W, R, F, J = mods.W, mods.R, mods.F, mods.J
    monkeypatch.setattr(C, "_now", lambda: 1_000_000.0)
    first = C.get_ctx(REF)
    calls = {n: spy(monkeypatch, o, n) for o, n in ((W, "runs"), (W, "asks"), (R, "step_rows"), (F, "functions"), (J, "events_after"))}
    again = C.get_ctx(REF)
    assert again is first and not any(calls.values()), {k: len(v) for k, v in calls.items()}
    for _ in range(50):
        assert C.get_ctx(REF) is first
    assert not any(calls.values())


def test_c13_a_change_rebuilds_after_the_floor_unless_touched(mods, monkeypatch):
    W, R = mods.W, mods.R
    now = [1_000_000.0]
    monkeypatch.setattr(C, "_now", lambda: now[0])
    first = C.get_ctx(REF)
    assert first.posts == []
    post(mods, "Identity", "Adaptation", "request", {"word": "line", "words": "x"})
    assert C.get_ctx(REF) is first, "inside the floor the read stands, though the board changed"
    now[0] += C.MIN_REBUILD_S + 0.1
    second = C.get_ctx(REF)
    assert second is not first and len(second.posts) == 1
    post(mods, "Identity", "Adaptation", "request", {"word": "line", "words": "y"})
    assert C.get_ctx(REF) is second
    C.touch(REF)
    third = C.get_ctx(REF)
    assert third is not second and len(third.posts) == 2
    assert C.get_ctx(REF) is third, "touch lifts the wait once"
    # a new ten-second tick is a new signature, but the floor still holds
    now[0] += 11
    assert C.get_ctx(REF) is not third


# ---- C1-4: journal tails ----------------------------------------------------------------------------------------------
def test_c14_the_tail_reads_only_what_was_appended(tmp_path):
    p = tmp_path / "board.jsonl"
    rows = [json.dumps({"n": i, "src": "Identity", "payload": {"words": "w" * 40}}) for i in range(1, 5001)]
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    t = C.JournalTail(p)
    got = t.rows()
    assert len(got) == 5000 and t.last_read == p.stat().st_size and t.bytes_read == t.last_read
    before = t.bytes_read
    assert len(t.rows()) == 5000 and t.last_read == 0 and t.bytes_read == before
    extra = json.dumps({"n": 5001, "src": "Owner"}) + "\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(extra)
    got = t.rows()
    assert len(got) == 5001 and got[-1]["n"] == 5001 and t.last_read == len(extra.encode("utf-8"))
    assert len(t.rows()) == 5001 and t.last_read == 0
    assert got is not t.rows(), "each call hands out its own list"


def test_c14_a_torn_line_is_skipped_and_a_truncated_journal_is_read_again(tmp_path):
    p = tmp_path / "steps.jsonl"
    p.write_text('{"n": 1}\n{"n": 2}\n{"n": 3, "torn', encoding="utf-8")
    t = C.JournalTail(p)
    assert [r["n"] for r in t.rows()] == [1, 2], "the unfinished line is left unread"
    with open(p, "a", encoding="utf-8") as f:
        f.write('x\n{"n": 4}\n')                          # the torn line is now a whole line that is not JSON: skipped, as record.lines skips it
    assert [r["n"] for r in t.rows()] == [1, 2, 4]
    p.write_text('{"n": 9}\n', encoding="utf-8")            # shorter: read again whole
    assert [r["n"] for r in t.rows()] == [9]
    os.remove(p)
    assert t.rows() == []
    p.write_text('{"n": 5}', encoding="utf-8")             # a last line with no newline that parses is a row (record.lines reads it)
    assert [r["n"] for r in t.rows()] == [5]
    with open(p, "a", encoding="utf-8") as f:
        f.write('\n{"n": 6}\n')
    assert [r["n"] for r in t.rows()] == [5, 6]


def test_c14_a_replaced_journal_is_read_again(tmp_path):
    p = tmp_path / "j.jsonl"
    p.write_text('{"n": 1}\n{"n": 2}\n', encoding="utf-8")
    t = C.JournalTail(p)
    assert len(t.rows()) == 2
    q = tmp_path / "other"
    q.write_text('{"n": 7}\n{"n": 8}\n{"n": 9}\n', encoding="utf-8")
    os.replace(q, p)                                        # another inode, and longer
    assert [r["n"] for r in t.rows()] == [7, 8, 9]


def test_c14_the_ledger_is_read_from_its_last_seq(mods, monkeypatch):
    m = mods
    cycle(m, "running", 6)
    for i in range(3):
        event(m, "slot.assigned", key="k%d" % i)
    calls = spy(monkeypatch, m.J, "events_after")
    monkeypatch.setattr(C, "_now", lambda: 1_000_000.0)
    c = C.get_ctx(REF)
    assert [e["seq"] for e in c.events] == [1, 2, 3] and [a[1] for a in calls] == [0]
    event(m, "run.started", key="k9")
    C.touch(REF)
    c = C.get_ctx(REF)
    assert [e["seq"] for e in c.events] == [1, 2, 3, 4] and [a[1] for a in calls] == [0, 3], "only after seq 3"
    C.touch(REF)
    C.get_ctx(REF)
    assert [a[1] for a in calls] == [0, 3], "a ledger that did not grow is not read"


# ---- C1-5: the home is part of the key --------------------------------------------------------------------------------
def test_c15_two_homes_reusing_a_ref_never_see_each_other(mods, tmp_path, monkeypatch):
    m = mods
    post(m, "Identity", "Adaptation", "request", {"word": "line", "words": "in the first home"})
    first = C.get_ctx(REF)
    assert len(first.posts) == 1 and first.d["name"] == "City Care Hospital Website"
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "second-home"))
    m.W.create(REF, "Another Website", None, kind="website")
    second = C.get_ctx(REF)
    assert second is not first and second.d["name"] == "Another Website" and second.posts == []
    monkeypatch.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp_path / "departments"))
    assert C.get_ctx(REF) is first, "the first home's read is still the first home's"


# ---- C1-6: nothing private, no path of this machine -------------------------------------------------------------------
def test_c16_clean_keeps_relative_paths_and_dates_and_shortens_machine_paths(machine):
    machine("/Users/x")
    got = C.clean({"file": "build/v1/index.html", "when": "due 5/6/2026 and 24/7/365", "words": "see /Users/x/y/z.txt.",
                   "win": "C:\\Users\\x\\f.txt now", "home": "in ~/notes/a.md, ok", "tmp": "/private/var/folders/ab/cd/ef.json",
                   "url": "https://example.test/var/log/x", "token": "t", "nested": [{"Password": "p", "keep": "ok"}], "n": 3})
    assert got["file"] == "build/v1/index.html" and got["when"] == "due 5/6/2026 and 24/7/365"
    assert got["words"] == "see z.txt." and got["win"] == "f.txt now" and got["home"] == "in a.md, ok"
    assert got["tmp"] == "ef.json" and got["url"] == "https://example.test/var/log/x"
    assert "token" not in got and got["nested"] == [{"keep": "ok"}] and got["n"] == 3
    assert C.clean("/Users/x/y/z.txt") == "z.txt" and C.clean(("a", "/Users/x/hosts")) == ["a", "hosts"]


OWNER_ROUTES = ("Make /home the landing page", "keep /private hidden", "see /var and /tmp and /etc", "the /opt-in page", "send /root to /login",
                "/home", "/private", "/var", "/tmp", "/etc", "/opt", "/root", "/Users", "/Volumes", "/opt-in", "/home/ and /root/ are pages",
                "Q&A:/faq and ratio 1:/2", "about~/home and a~/b", "see /homepage and /rooted and /variable")


@pytest.mark.parametrize("words", OWNER_ROUTES)
def test_c16_a_route_in_the_owners_words_is_not_a_machine_path(words):
    """A path of this machine has a root AND something under it; '/home', '/private' or '/opt-in' alone are a website's pages."""
    assert C.clean(words) == words
    assert C.clean({"text": words, "who": "identity"})["text"] == words


@pytest.mark.parametrize("home", ["/Users/me", "/home/me"])
def test_c16_a_machine_path_is_still_shortened_wherever_it_stands(machine, home):
    machine(home, temp="/tmp/pytest-of-me")
    for text, want in (("wrote %s/.sutra-ui/departments/x/dept.json now" % home, "wrote dept.json now"), ("(%s/a.md)" % home, "(a.md)"),
                       ("in /tmp/pytest-of-me/t1/x.txt.", "in x.txt."), ("at /private/var/folders/ab/T/x/", "at x"), ("\"%s/hosts\"" % home, "\"hosts\""),
                       ("C:/Users/me/f.txt and D:\\x\\y.md", "f.txt and y.md"), ("saved to ~/notes/a.md", "saved to a.md"),
                       ("/Volumes/Disk/site/index.html", "index.html"), ("%s/bin/x;" % home, "x;"), ("%s." % home, "me."),
                       ("see %s/a and %s/b" % (home, home), "see a and b")):
        assert C.clean(text) == want, text


def test_c16_the_folders_of_this_machine_are_what_the_rule_is_built_from(mods, machine, tmp_path):
    """Path.home(), the records' home, the temp folder and the app's own folder, as named and as the disk resolves them."""
    machine("/Users/me", temp=str(tmp_path / "tmp"))
    roots = C._machine_roots()
    for want in ("/Users/me", str(mods.home / "departments"), os.path.realpath(mods.home / "departments"), str(tmp_path / "tmp"),
                 os.path.realpath(tmp_path / "tmp"), str(UI), "/private/var/folders", "/Volumes"):
        assert want in roots, want
    assert "/" not in roots and all(r.startswith("/") and not r.endswith("/") for r in roots)
    assert C.clean(str(mods.home / "departments" / "d1" / "dept.json")) == "dept.json"
    assert C.clean(str(UI / "j2ui_common.py")) == "j2ui_common.py"
    assert C.ABS_PATH.search("/Users/me/a") and not C.ABS_PATH.search("/Users/you/a"), "the rule of the moment is the machine of the moment"


#: pages of the owner's site that look like the path of a machine: none is under a folder of this one (HOME is /Users/me)
SITE_ROUTES = ("go to /home/about", "Never link /private/area and always keep /home/about first", "/private/members", "/etc/terms and /var/news",
               "/opt/shop/cart", "/tmp/stage/a", "/root/x/y", "/Users/login/settings", "see /home/about/team.", "(/home/about)", '"/private/members/"',
               "Plan B:/pricing", "Plan B:/pricing/page", "a:/b/c", "C:/pricing/page", "Q&A:/faq/page", "keep /home/about, /private/area and /var/news")


@pytest.mark.parametrize("words", SITE_ROUTES)
def test_c16_a_route_quoted_in_an_ask_is_unchanged(machine, words):
    """The verifier's finding N1: the path rule rewrote the owner's quoted routes ('go to /home/about' became 'go to about',
    'Plan B:/pricing' became 'Plan pricing'). A path is this machine's only under its own folders, so a route is left alone
    wherever it stands: a bare string, a message, an ask, a condition, a rubric row, a nested list."""
    machine("/Users/me")
    assert C.clean(words) == words
    body = {"chat": [{"id": 1, "who": "identity", "text": "@Requester A rule, as understood: " + words, "to_user": True, "act": "ASK_REQUESTER"},
                     {"id": 2, "who": "adaptation", "text": "Proposed the plan to Priority: " + words}],
            "paused": {"kind": "approval", "questions": [{"question": "A rule, as understood: " + words, "options": ["Stamp", "Say no"]}], "msg": 1,
                       "label": words, "choices": None},
            "conditions": {"D1": {"text": words, "items": [words]}}, "rubric": [{"id": "D1", "criterion": words, "how": "an AI reads it"}]}
    assert C.clean(body) == body


def test_c16_a_drive_letter_is_a_drive_only_where_a_windows_path_follows(machine):
    machine("/Users/me")
    assert C.clean("Plan B:/pricing and C:/Users/me/f.txt and D:\\x\\y.md and E:/Program/z") == "Plan B:/pricing and f.txt and y.md and E:/Program/z"
    assert C.clean("C:/ProgramData/x/y.cfg and C:/Windows/System32/a.dll") == "y.cfg and a.dll"


#: strings the two scrubs must say the same: pages of the owner's site, a relative file, a date, a URL, and paths of this machine (HOME is /Users/me)
SAME_BOTH_WAYS = SITE_ROUTES + OWNER_ROUTES + (
    "build/v1/index.html opens on 5/6/2026 and 24/7/365", "https://example.test/var/log/x", "wrote /Users/me/y/z.txt.", "C:\\Users\\me\\f.txt now",
    "in ~/notes/a.md, ok", "/private/var/folders/ab/cd/ef.json", "(/Users/me/a) and \"/Users/me/b/c.md\"", "Plan B:/pricing and C:/Users/me/f.txt")


@pytest.mark.parametrize("words", SAME_BOTH_WAYS)
def test_c16_functions_view_and_the_adapter_scrub_with_one_rule(machine, words):
    """Finding N1, third part. functions_view's own path rule cut any /a/b, so what the adapter read from it (the Audit tab, the lanes,
    the Map) was already cut when the adapter's rule, which keeps the owner's pages, saw it. Both scrub by machine_paths now: a
    string comes out of functions_view as it comes out of the adapter, and neither makes 'build/v1/index.html' into 'buildindex.html'."""
    machine("/Users/me")
    assert FV._clean(words) == C.clean(words) == MP.shorten(words)
    assert FV._clean({"a": [words, {"b": words}], "token": "t"}) == {"a": [FV._clean(words), {"b": FV._clean(words)}]}


def test_c16_the_path_rule_is_a_module_of_its_own_that_neither_reader_owns():
    """functions_view cannot read j2ui_common (j2ui_common reads functions_view), so the rule is machine_paths': it reads neither."""
    tree = ast.parse((UI / "machine_paths.py").read_text())
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
        {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not [m for m in imported if m == "functions_view" or m.startswith("j2ui_")], imported
    assert C.ABS_PATH is MP.ABS_PATH and C.shorten is MP.shorten and FV.MP is MP


def test_c16_the_owners_own_words_are_never_rewritten_even_when_they_name_a_path_shaped_page(machine):
    machine("/Users/me")
    mine = "keep /home/about, /private/area and /var/news; /Users/login is the sign-in"
    got = C.clean({"chat": [{"id": 1, "who": "user", "text": mine, "token": "t"}, {"id": 2, "who": "identity", "text": "@Requester wrote /Users/me/x/a.txt"}],
                   "goal": {"statement": mine, "rules": ["never: " + mine], "done_when": [mine], "to_be_confirmed": [{"criterion": mine, "fact": mine}],
                            "secret": "s"}, "other": mine})
    assert got["chat"][0] == {"id": 1, "who": "user", "text": mine}, "the owner's message, only its private keys are dropped"
    assert got["chat"][1]["text"] == "@Requester wrote a.txt", "what a function says of a file is machine-written"
    assert got["goal"] == {"statement": mine, "rules": ["never: " + mine], "done_when": [mine], "to_be_confirmed": [{"criterion": mine, "fact": mine}]}
    assert got["other"] == mine, "a route quoted in an ask is unchanged: it is not under a folder of this machine"


def test_c16_a_line_that_carries_the_owners_words_is_sent_as_it_is_and_only_its_lead_passes_the_path_rule(machine):
    """owner_words.kept leaves the owner's words (an ask's `words`) alone; the path rule must too, even for a path under this
    machine's home, while the lead the machine wrote is shortened as everywhere else."""
    machine("/Users/me")
    words = "keep /Users/me/site/index.html as it is, and /home/about too"
    line = C.said("Write the page at /Users/me/work/out.txt: " + words, words)
    assert isinstance(line, C.Said) and line == "Write the page at out.txt: " + words
    assert C.clean({"text": line, "more": [line], "token": "t"}) == {"text": line, "more": [line]}
    assert json.loads(json.dumps({"q": line})) == {"q": line}, "it is a string to everything that reads it"
    assert C.clean("Write the page at /Users/me/work/out.txt: " + words) == "Write the page at out.txt: keep index.html as it is, and /home/about too"
    plain = C.said("Write the page at /Users/me/work/out.txt", None)
    assert plain == "Write the page at /Users/me/work/out.txt" and not isinstance(plain, C.Said), "no words: all the machine's, and clean() has it"
    assert C.said("a granted line", "b") == "a granted line" and C.said(None, "b") is None


def identity(mods, ref=REF):
    """Identity's node in the Ctx's read of the functions (what the lanes and the Map print), read afresh."""
    C.touch(ref)
    return next(n for n in C.get_ctx(ref).fv["functions"] if n["fn"] == "identity")


def test_c16_the_line_identity_waits_on_the_owner_with_keeps_the_owners_routes(mods, machine):
    """Finding N1, second part. functions_view used to scrub its read with a path rule of its own, to which any /a/b was a path, so the ask
    it quotes came out as 'Never link area from the menu and keep about first': the Identity lane and the Map node said a rule
    that was not the one the owner is asked to stamp. The line is made from the ask itself, as the pause says it."""
    machine("/Users/me")
    rule = "A rule, as understood: Never link /private/area from the menu and keep /home/about first; Plan B:/pricing stays"
    ask(mods, "rule", id="a-rule", engine="Identity", text=rule)
    node = identity(mods)
    assert (node["state"], node["word"], node["line"]) == ("waiting_on_you", "waits on you", rule)
    assert not isinstance(node["line"], C.Said), "no words of the owner's end it: clean() has the lead"
    # a relative file and a date are not routes and not paths: they stay as they are too
    plain = "Open build/v1/index.html on 5/6/2026 and keep /home/about"
    ask(mods, "rule", id="a-rule", engine="Identity", text=plain)
    assert identity(mods)["line"] == plain


def test_c16_the_owners_words_that_end_the_ask_are_the_lines_own_and_the_lead_passes_the_path_rule(mods, machine):
    machine("/Users/me")
    words = "keep /Users/me/site/index.html as it is, and /home/about too"
    ask(mods, "step", id="a-out", engine="Write", text="Write the page at /Users/me/work/out.txt: " + words, words=words)
    line = identity(mods)["line"]
    assert isinstance(line, C.Said) and line == "Write the page at out.txt: " + words
    assert C.clean({"doing": line}) == {"doing": line}, "clean() sends it as it is"
    # cut to the line functions_view cuts to (140), still the owner's after the cut
    long_words = "keep /home/about and /private/area first; " + "and more " * 30 + "/Users/me/site/index.html"
    ask(mods, "step", id="a-out", engine="Write", text="Write the page at /Users/me/work/out.txt: " + long_words, words=long_words)
    cut = identity(mods)["line"]
    assert isinstance(cut, C.Said) and len(cut) <= 140 and cut.endswith("…")
    assert cut.startswith("Write the page at out.txt: keep /home/about and /private/area first; and more"), cut


def test_c16_the_ask_the_line_is_made_of_is_the_one_functions_view_picks(mods):
    """Identity's open question, else a finding, else the oldest pending ask: the lane says the same ask as before the line was
    made again (the texts carry no route, so functions_view's scrub changes nothing and its line is the one to match)."""
    def said_by_fv():
        return next(n for n in mods.F.functions(REF)["functions"] if n["fn"] == "identity")["line"]
    ask(mods, "publish", id="a-1", engine="Publish", text="Publish: go live for the first time")
    assert identity(mods)["line"] == said_by_fv() == "Publish: go live for the first time"
    ask(mods, "finding", id="a-2", engine="Audit", text="Audit found a page nobody can reach")
    assert identity(mods)["line"] == said_by_fv() == "Audit found a page nobody can reach"
    ask(mods, "j2_identity", id="a-3", engine="Identity", text="What is the school called?")
    cycle(mods, "waiting", 1, open_ask="a-3")
    assert identity(mods)["line"] == said_by_fv() == "What is the school called?"


def test_c16_functions_views_own_line_keeps_the_owners_routes_too(mods, machine):
    """The line is made again here only to keep the owner's own words (a Said); the pages the owner quotes in an ask no longer
    need it: functions_view's own line carries them, so a lane or a Map node that is not made again (a function's other lines)
    would not cut them either."""
    machine("/Users/me")
    text = "A rule, as understood: Never link /private/area from the menu and keep /home/about first"
    ask(mods, "rule", id="a-rule", engine="Identity", text=text)
    by_fv = next(n for n in mods.F.functions(REF)["functions"] if n["fn"] == "identity")["line"]
    assert by_fv == text == identity(mods)["line"]


def test_c16_a_line_that_is_not_an_asks_is_left_as_functions_view_said_it(mods):
    ask(mods, "step", id="a-w", engine="Write", text="Write the page")
    cycle(mods, "blocked", 4)
    assert identity(mods)["line"] == "the plan was dropped; it needs your words", "a plan dropped is not the ask's line"
    cycle(mods, "done", 8)
    node = identity(mods)
    assert (node["state"], node["line"]) == ("quiet", ""), "a department that is done is quiet throughout"
    cycle(mods, "waiting", 1)
    ask(mods, "step", id="a-w", engine="Write", text="")
    assert identity(mods)["line"] == "waits for your answer", "an ask with no words says that it waits"


def test_c16_a_line_that_cannot_be_made_again_keeps_functions_views_and_says_why(mods, monkeypatch):
    ask(mods, "publish", id="a-1", engine="Publish", text="Publish: go live for the first time")
    monkeypatch.setattr(C, "_asked", lambda c: 1 / 0)
    C.touch(REF)
    c = C.get_ctx(REF)
    node = next(n for n in c.fv["functions"] if n["fn"] == "identity")
    assert node["line"] == "Publish: go live for the first time" and "owner line: ZeroDivisionError" in c.reasons


def test_c16_times():
    assert C.hhmmss("2026-10-26T22:44:21+05:30") == "22:44:21" and C.hhmmss("nonsense") == "" and C.hhmmss(None) == ""
    assert C.epoch("2026-10-26T22:44:21+05:30") - C.epoch("2026-10-26T22:44:20+05:30") == 1.0
    assert C.epoch("") == 0.0 and C.epoch("x") == 0.0


# ---- C1-7: a department with nothing in it, and a sub-read that breaks ------------------------------------------------
def test_c17_no_cycle_is_not_started_and_every_attribute_is_there(mods):
    c = C.get_ctx(REF)
    assert c.state == "not_started" and c.ref == REF and c.kind == "website" and c.doc is False and c.stopped is False
    for name in ("d", "root_ref", "fv", "cur", "runs", "asks", "posts", "root_posts", "steps", "events", "engines", "planned", "arts",
                 "chat", "msg_of", "ask_msg", "ask_opts", "paused_ask", "reasons", "memo"):
        assert hasattr(c, name), name
    assert c.d["ref"] == REF and c.root_ref is None and c.cur == {} and c.root_posts == [] and c.memo == {}
    assert [a["name"] for a in c.arts] == ["Brief", "Site plan", "Pages", "Build", "Live site"]
    assert c.planned is True and [e["wid"] for e in c.engines] == ["W-1", "W-2", "W-3", "W-4"], "no cycle: the line it was born with is its plan"
    assert c.reasons == []


def test_c17_a_cycle_with_no_registered_plan_numbers_no_engine(mods):
    cycle(mods, "adapting", 2)
    c = C.get_ctx(REF)
    assert c.state == "adapting" and c.planned is False
    assert all(e["wid"] is None and e["k"] is None for e in c.engines) and c.who("Plan") is None and c.dest("Plan") is None


def test_c17_a_broken_read_leaves_its_attribute_empty_and_says_why(mods, monkeypatch):
    def boom(ref):
        raise RuntimeError("the file is gone")
    monkeypatch.setattr(mods.W, "runs", boom)
    c = C.get_ctx(REF)
    assert c.runs == [] and any(r.startswith("runs: RuntimeError") for r in c.reasons), c.reasons
    assert c.d["ref"] == REF and c.state == "not_started", "the rest of the read stands"


def identity_asks(m, ref=REF, question="What evidence will prove this site is done?"):
    """Identity's question put the way the ledger puts it (J.asked: a j2_identity ask, which has no `engine` key)."""
    d = m.W.dept(ref)
    d["events"] = [{"kind": "j2_ready", "route": "template"}]
    m.W.save_dept(ref, d)
    if not m.J._state(ref):
        m.J.begin(ref)
    cur = m.J.asked(ref, question, ["done-when"], "Identity's standard is not met yet: done-when", standard=False)
    assert cur["open_ask"] and "engine" not in next(a for a in m.W.asks(ref) if a["id"] == cur["open_ask"])
    return cur


def test_c17_identitys_open_question_does_not_take_the_engines_away(mods):
    """An ask with no `engine` key (Identity's question) is pending; the engines, the plan flag and the W-k numbering are never empty."""
    identity_asks(mods)
    mods.W.map_view(REF)                                       # the record's own reader reads it too (it raised KeyError before views fix 1)
    C.touch(REF)
    c = C.get_ctx(REF)
    assert c.state == "waiting" and c.paused_ask and c.paused_ask["form"] == "words"
    assert c.reasons == [], c.reasons
    assert [e["name"] for e in c.engines] == ["Plan", "Write", "Check", "Publish"] and c.planned is False
    assert all(e["wid"] is None and e["in_line"] and e["state"] == "Idle" and e["steps_view"] for e in c.engines), "no plan is registered yet: no W-k"


def test_c17_the_engines_read_the_same_with_and_without_the_question(mods, born, tick):
    ref = born()
    C.reset_caches()
    before = C.get_ctx(ref)
    assert before.planned and [e["wid"] for e in before.engines] == ["W-1", "W-2", "W-3", "W-4"]
    identity_asks(mods, ref)
    C.touch(ref)
    after = C.get_ctx(ref)
    assert after.reasons == [], after.reasons
    keys = ("k", "wid", "name", "reads", "writes", "runs_as", "in_line", "env", "window_min", "timetable")
    assert [{k: e[k] for k in keys} for e in after.engines] == [{k: e[k] for k in keys} for e in before.engines]
    assert after.planned is True and [e["state"] for e in after.engines] == [e["state"] for e in before.engines]
    assert after.wid("Write") == "W-2" and after.who("Check") == "W-3"


def test_c17_a_pending_ask_for_an_engine_still_makes_that_engine_wait_when_the_map_is_rebuilt(mods):
    ask(mods, "publish", engine="Publish")
    identity_asks(mods)
    c = C.get_ctx(REF)
    assert c.reasons == [] and {e["name"]: e["state"] for e in c.engines}["Publish"] == "Waits"


def test_c17_the_rebuilt_engines_are_the_maps_own_rows(mods, born, tick):
    """The by-hand rows must stay map_view's rows, or the numbering would change the moment Identity asks."""
    import owner_words

    def same(ref):
        C.touch(ref)
        c = C.get_ctx(ref)
        want = owner_words.map_view(mods.W.map_view(ref))
        got = C._engines_by_hand(c)
        assert got["planned"] == want["planned"] and got["engines"] == want["engines"], ref
    same(REF)                                                  # born, no cycle: the line it was born with
    cycle(mods, "adapting", 2)
    run(mods, "Write")
    ask(mods, "publish", engine="Publish")
    same(REF)                                                  # a cycle with no plan, one engine running, one waiting
    ref = born()
    same(ref)                                                  # a registered plan, as Root sets it up
    mods.W.run_until_idle(ref, limit=50)
    d = mods.W.dept(ref)
    d["stopped"] = True
    mods.W.save_dept(ref, d)
    same(ref)                                                  # stopped


def test_c17_when_the_rebuild_fails_too_the_engines_are_empty_and_the_reason_stands(mods, monkeypatch):
    identity_asks(mods)
    monkeypatch.setattr(mods.W, "engine_view", lambda ref, name: (_ for _ in ()).throw(RuntimeError("gone")))
    C.touch(REF)
    c = C.get_ctx(REF)
    assert c.engines == [] and c.planned is False and c.reasons == ["map: RuntimeError"], c.reasons


def test_c17_a_ref_with_no_folder_still_gives_a_ctx(mods):
    c = C.get_ctx("dref-never-made")
    assert c.d == {} and c.runs == [] and c.chat == [] and c.state == "not_started"


# ---- C1-8: numbering and who said it ----------------------------------------------------------------------------------
def test_c18_numbers_who_dest_and_step_at(mods, born, tick):
    ref = born()
    C.reset_caches()
    c = C.get_ctx(ref)
    assert c.planned and [e["wid"] for e in c.engines] == ["W-1", "W-2", "W-3", "W-4"]
    assert [e["name"] for e in c.engines] == ["Plan", "Write", "Check", "Publish"] and [e["k"] for e in c.engines] == [1, 2, 3, 4]
    assert c.wid("Check") == "W-3" and c.wid("Nobody") is None
    assert c.who("Owner") == "user" and c.who("Identity") == "identity" and c.who("priority") == "priority"
    assert c.who("Plan") == "W-1" and c.who("Root") is None and c.who("Stranger") is None
    assert c.dest("Owner") == "user" and c.dest("Audit") == "audit" and c.dest("Publish") == "W-4" and c.dest("Root") is None
    assert c.fn_id("Identity") == "fn:identity" and c.fn_id("Plan") is None
    assert c.root_ref and c.root_posts and c.posts and c.steps and c.events and c.runs
    assert all(e["state"] for e in c.engines) and c.engines[0]["steps_view"]["name"] == "Plan"
    assert [r["engine"] for r in c.engines[0]["runs"]] == ["Plan"] or c.engines[0]["runs"] == [r for r in c.runs if r["engine"] == "Plan"]
    # the step of the latest event not after a time
    assert c.step_at("1999-01-01T00:00:00+00:00") is None
    last = c.events[-1]
    assert c.step_at(last["occurred_at"]) == last["step"]
    first = c.events[0]
    assert c.step_at(first["occurred_at"]) in range(1, 9)
    assert [a["name"] for a in c.arts][:2] == ["Brief", "Site plan"] and c.arts[0]["latest"]["v"] == c.arts[0]["versions"][-1]["v"]
    # clean in the owner's words: the engine cards come through owner_words
    assert "GRANT" not in json.dumps(c.engines, default=str)
