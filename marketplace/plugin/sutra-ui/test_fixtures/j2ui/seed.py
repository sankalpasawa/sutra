"""seed.py -- departments in every state the J2 page can be in, for the contract, hostile-string and Chrome tests
(UI port, package j2ui-verify, T3).

    seed(tmp, state, env=None, ref=None, m=None) -> (ref, m)

creates a runtime-2 website department through website_dept.create on fresh records homes under `tmp` and sets it to `state`
the way the app finds it (the helpers are core_fixtures', which are test_functions_view.py's: cycle, ask, thread, run).
`m` is what the `mods` fixture gives (m.W website_dept, m.R engine_runtime, m.J j2_runtime, m.F functions_view, m.C j2ui_common,
m.ref, m.home) plus `m.root` (the Root's ref when the state has one) and `m.env`. `env` is a monkeypatch (setenv, delenv) in a
test; without one the process environment is set, which is what a dev server for the Chrome walk wants. Pass the `m` of an earlier
call (and a `ref` of its own) to put a second department on the same homes: only the states in HOMED can sit on a home that
already has one, because the others are written at REF.

States (states()): every row of test_j2ui_state.STATE_TABLE, which is the one table of what each cycle state says
    not_started assessing waiting adapting bargaining closing checking reshaping running running_with_a_publish_ask blocked
    pursuing unread done done_with_an_item_to_confirm done_with_a_finding_asked stopped
and the departments the contract needs besides (EXTRAS):
    two_publish_asks  two publish asks pending while the line re-ran (Build v1 and v2): each ask has its thread, none its card
    root_follow_up    a Root and its department, the owner's follow-up said to the Root (the words reach the department by Root)
    running_line      Root's check has registered the plan; Plan and Write have filed (Site plan, Pages) and Check is running
    with_board        the same, and two questions on the board between the engines (questions.json: one answered, one open)
    pursuing_line     the whole line filed, Audit found something and Identity asks the owner to put it right (a finding)
    filed             the whole line filed with real pages (Brief, Site plan, Pages, Build, Live site), a clean reading, nothing waiting
    default_kind      a department of kind default under a Root: the J2 view is not for either (404 on every route)
and the four the Chrome walk uses (qa/walks/j2ui-e2e.sh; HOMED):
    start       a department nothing has been said to: the page's start screen
    question    the department as a person makes it (found an organisation, said the words, Root set it up, the line ran to its first
                question): Identity asks whether the site may go live, with Stamp and Say no
    ready       the same, stamped and read by Audit with nothing to put right: the page's "Your website is ready" card
    hostile     a department whose every string is an attacker's (see hostile())

As a script:  python test_fixtures/j2ui/seed.py <home-dir> <state> [<state> ...]
writes the departments of the HOMED states under <home-dir> (one set of homes) and prints one line per state: `<state> <ref> <root or ->`.
"""
import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
UI = HERE.parents[1]
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))

REF = "dref-j2c0001"
ROOT = "dref-j2root1"
WEBSITE = "Build a website that teaches algebra to Class 8 students"
EXTRAS = ("two_publish_asks", "root_follow_up", "running_line", "with_board", "pursuing_line", "filed", "default_kind")
HOMED = ("start", "question", "ready", "hostile")
ALIASES = {"not_yet": "not_started"}
READING = {"read": 1, "met": ["D1"], "not_met": [], "to_confirm": [], "high": []}


class _Env:
    """The process environment, with the two calls of a monkeypatch the seed uses."""

    def setenv(self, name, value):
        os.environ[name] = str(value)

    def delenv(self, name, raising=True):
        os.environ.pop(name, None)


def table():
    """test_j2ui_state.STATE_TABLE as {name: setup(m)}. Imported when asked, so a script that needs only `ready` reads no tests."""
    import test_j2ui_state as T
    return {row[0]: row[1] for row in T.STATE_TABLE}


def states():
    return tuple(table()) + EXTRAS + HOMED


def boot(tmp, env=None):
    """Fresh records homes under tmp, the modules reloaded on them, every j2ui cache empty: the namespace of the `mods` fixture."""
    env = env or _Env()
    tmp = Path(tmp)
    env.setenv("SUTRA_NATIVE_DEPT_HOME", str(tmp / "departments"))
    env.setenv("SUTRA_NATIVE_HOME", str(tmp / "registry"))
    for var, sub in (("SUTRA_UI_PROPOSALS", "proposals"), ("SUTRA_UI_ROUTINES", "routines"), ("SUTRA_UI_RUNS", "runs")):
        (tmp / sub).mkdir(parents=True, exist_ok=True)
        env.setenv(var, str(tmp / sub))
    env.setenv("SUTRA_WEBSITE_OFFLINE", "1")
    env.setenv("J2_FLOW_V1", "1")
    env.delenv("SUTRA_ENGINE_RUNTIME", raising=False)
    import engine_runtime as R
    import functions_view as F
    import j2_runtime as J
    import website_dept as W
    for mod in (W, R, J, F):
        importlib.reload(mod)
    import j2ui_common as C
    C.reset_caches()
    return SimpleNamespace(W=W, R=R, J=J, F=F, C=C, ref=REF, home=tmp, root=None, env=env)


def born(m, words=WEBSITE, org="Acme Learning"):
    """The department as a person makes one: found an organisation, say the words to its Root, Root sets the department up and the
    line runs to its first question (the recipe of the UI port's reference probe). Sets m.root and m.ref; returns the ref."""
    m.env.setenv("J1_FLOW_V1", "1")
    import founding
    import org2_apply
    import placement_engine as E
    for mod in (E, org2_apply, founding):
        importlib.reload(mod)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, "Sutra", ["Sutra"], "T-local", origin="operator-request")
    root = founding.found_structure(org, owner="Sankalp")["root"]
    m.W.owner_ask(root, words)
    m.W.run_until_idle(root, limit=300)
    child = next(d for d in m.W.list_depts() if d.get("parent") == root)["ref"]
    m.W.run_until_idle(child, limit=300)
    m.root, m.ref = root, child
    return child


def stamp_all(m, ref):
    """The owner stamps every pending stamp ask and the line runs on (what a person does on the Needs-you card)."""
    for _ in range(6):
        pending = [a for a in m.W.asks(ref) if a.get("status") == "pending" and not a.get("options") and a.get("kind") != "j2_identity"]
        if not pending:
            break
        for a in pending:
            m.W.decide_ask(ref, a["id"], True)
        m.W.run_until_idle(ref, limit=300)
    return ref


def read_clean(m, ref, version=1, artifact="Live site"):
    """Audit read what went out and found nothing to put right: j2_runtime.audited records it and the goal is reached."""
    m.J.audited(ref, version, [], artifact=artifact, reading=dict(READING))


# ---- the extra departments ------------------------------------------------------------------------------------------------
def _two_publish_asks(m):
    from test_fixtures.j2ui import core_fixtures as K
    K.cycle(m, "running", 6)
    for i in (1, 2):
        m.W.add_version(REF, "Build", {"index.html": "<!doctype html><title>Home %d</title><p>version %d</p>" % (i, i)}, [], "r-b%d" % i,
                        {"ok": True, "notes": []})
        K.ask(m, "publish", id="a-pub%d" % i, thread="x-pub%d" % i, engine="Publish", text="Publish: go live, version %d" % i)
        K.thread(m, "Identity", "Owner", "request", "publish", tid="x-pub%d" % i, objective="say whether the site may go live",
                 about={"art": "Build", "v": i})


def _root_follow_up(m):
    ref = born(m)
    m.W.owner_ask(m.root, "Add a page about our pricing plans", about=ref)
    m.W.run_until_idle(m.root, limit=300)
    m.W.run_until_idle(ref, limit=300)
    return ref


PAGES = {"index.html": '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>City Care</title>'
                       '<link rel="stylesheet" href="style.css"></head><body><main><h1>City Care Hospital</h1><p>Open every day.</p>'
                       '<a href="about.html">About</a></main></body></html>',
         "about.html": '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>About</title>'
                       '<link rel="stylesheet" href="style.css"></head><body><main><h1>About us</h1><a href="index.html">Home</a></main></body></html>',
         "style.css": "body{font:16px system-ui;margin:2rem}h1{color:#134}"}
OK = {"ok": True, "notes": ["every link resolves"]}
FILING = (("Brief", {"brief.md": "A site for City Care Hospital."}, [], "owner"),
          ("Site plan", {"site-plan.json": '{"pages": ["index", "about"]}'}, [{"art": "Brief", "v": 1}], "r-plan"),
          ("Pages", {k: v for k, v in PAGES.items() if k.endswith(".html")}, [{"art": "Site plan", "v": 1}], "r-write"),
          ("Build", PAGES, [{"art": "Pages", "v": 1}], "r-build"),
          ("Live site", PAGES, [{"art": "Build", "v": 1}], "r-pub"))


def register_line(m, ref=REF, left=()):
    """Root's check has registered the plan: Coordination's table says so, with the engines of the line and the ones left out."""
    t = dict(m.R.coordination(ref))
    t["registered"] = 1
    t["line"] = [e for e in t["line"] if e not in left]
    t["left_out"] = [{"engine": e, "in_line": False, "since": m.W.now()} for e in left]
    m.W._write(m.W.ddir(ref) / "coordination.json", t)


ENGINES = ("Plan", "Write", "Check", "Publish")


def file_line(m, upto, ref=REF):
    """The first `upto` artifacts of the line each filed with one version, a step row for each step of each engine that filed one
    (its run is `r-<engine>-ok`, which the caller records with core_fixtures.run), as the runtime writes them."""
    import versions as VERS                       # the check is the one given: website_dept.add_version would fold the Library's own in
    for i, (art, files, read, run_id) in enumerate(FILING[:upto]):
        run_id = "r-%s-ok" % ENGINES[i - 1].lower() if i else run_id
        VERS.add(m.W._abase(ref, art), files, read, run_id, {"ok": True, "notes": []} if run_id == "owner" else OK, m.W.now())
    for engine in ENGINES[:max(0, upto - 1)]:
        for step in m.R.all_steps(engine):
            m.R._append(ref, "steps.jsonl", {"engine": engine, "step": step["id"], "mode": "slot", "rung": "C2", "check": OK, "answer": None,
                                             "usd": 0.0, "calls": 1, "ms": 5, "status": "ok", "run": "r-%s-ok" % engine.lower(),
                                             "started": m.W.now(), "ended": m.W.now()})


def _running_line(m):
    from test_fixtures.j2ui import core_fixtures as K
    K.cycle(m, "running", 6)
    register_line(m)
    file_line(m, 3)
    K.run(m, "Plan", status="ok", id="r-plan-ok", slot="Plan@brief.v1", spend={"calls": 1, "usd": 0.02})
    K.run(m, "Write", status="ok", id="r-write-ok", slot="Write@site-plan.v1", spend={"calls": 3, "usd": 0.08})
    K.run(m, "Check", status="running", id="r-check-run", slot="Check@pages.v1", what="Check the pages")
    K.event(m, "identity.assessed", actor="Identity", step=1, summary="The identity is good enough to start on.")


def _with_board(m):
    _running_line(m)
    rows = [{"schema": "board/1", "id": "Q-1", "asked_by": "Write", "to": "Plan", "about": "the page list", "question": "Which pages does the site have?",
             "answer": "Home and About", "answered_by": "Plan", "status": "answered", "artifact_update": None, "used_by": ["Check"],
             "cycle": "cycle-test", "slot": "Write@site-plan.v1", "attempt": 1, "run": None},
            {"schema": "board/1", "id": "Q-2", "asked_by": "Check", "to": "Write", "about": "the about page", "question": "Is the hours line on the about page?",
             "answer": None, "answered_by": None, "status": "open", "artifact_update": None, "used_by": [], "cycle": "cycle-test",
             "slot": "Check@pages.v1", "attempt": 1, "run": None}]
    m.W._write(m.W.ddir(REF) / "questions.json", {"schema": "board/1", "entries": rows})


def _finished(m, state):
    from test_fixtures.j2ui import core_fixtures as K
    K.cycle(m, state, 8)
    register_line(m)
    file_line(m, 5)
    for eng in ("Plan", "Write", "Check", "Publish"):
        K.run(m, eng, status="ok", id="r-%s-ok" % eng.lower(), slot="%s@x.v1" % eng, spend={"calls": 2, "usd": 0.05})
    K.event(m, "identity.assessed", actor="Identity", step=1, summary="The identity is good enough to start on.")


def _pursuing_line(m):
    from test_fixtures.j2ui import core_fixtures as K
    _finished(m, "pursuing")
    found = [{"page": "index.html", "claim": "the page says 'to be confirmed' where the hours should be", "severity": "high"},
             {"page": None, "claim": "a link to the car park has no address", "severity": "low"}]
    K.thread(m, "Audit", "Identity", "inform", "finding", tid="x-find1", claim=found[0]["claim"], severity="high", findings=found, about_version=1,
             about={"art": "Live site", "v": 1})
    K.stamp_ask(m, "finding", text="Audit found: the home page has no hours. Stamp to have it put right.", tid="x-find-ask")


def _filed(m):
    """The whole line filed with real pages and a clean reading: what a finished department leaves."""
    from test_fixtures.j2ui import core_fixtures as K
    _finished(m, "done")
    K.event(m, "audit.finding_filed", actor="Audit", recipient="Identity", step=7, summary="Audit read Live site v1 and found nothing to put right.",
            state="recorded", payload={"severity": "none", "findings": 0}, evidence_refs=[{"artifact": "Live site", "version": 1}])


def _default_kind(m):
    m.W.create("dref-default1", "Billing", "Billing", kind="default")
    m.W.create(ROOT, "Acme Root", "Makes departments", kind="root")
    m.root = ROOT


def start(m, ref="dref-start1"):
    """A department nothing has been said to."""
    m.W.create(ref, "City Care Hospital Website", None, kind="website")
    m.ref = ref
    return ref


def seed(tmp, state, env=None, ref=None, m=None):
    """A department in `state`: (ref, m). On fresh homes under tmp, or on those of `m` for a state in HOMED. KeyError for an unknown state."""
    name = ALIASES.get(state, state)
    if name not in states():
        raise KeyError(state)
    if m is not None and name not in HOMED:
        raise ValueError("%s is written at %s: it needs homes of its own" % (name, REF))
    m = m or boot(tmp, env)
    if name == "start":
        return start(m, ref or "dref-start1"), m
    if name == "question":
        return born(m, org="Acme Learning"), m
    if name == "ready":
        r = born(m, org="Beta Learning")
        stamp_all(m, r)
        read_clean(m, r)
        return r, m
    if name == "hostile":
        return hostile(m, ref or "dref-hostile1"), m
    if name == "root_follow_up":
        return _root_follow_up(m), m
    if name == "default_kind":
        _default_kind(m)
        return "dref-default1", m
    m.W.create(REF, "City Care Hospital Website", None, kind="website")
    if name == "two_publish_asks":
        _two_publish_asks(m)
    elif name == "running_line":
        _running_line(m)
    elif name == "with_board":
        _with_board(m)
    elif name == "pursuing_line":
        _pursuing_line(m)
    elif name == "filed":
        _filed(m)
    else:
        table()[name](m)
    m.C.touch(REF)
    return REF, m


def hostile(m, ref):
    raise NotImplementedError("the hostile department is written with T4")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python test_fixtures/j2ui/seed.py <home-dir> <state> [<state> ...]   (states: %s)" % " ".join(HOMED))
        sys.exit(2)
    shared = None
    for st in sys.argv[2:]:
        ref_, shared = seed(sys.argv[1], st, m=shared)
        print(st, ref_, shared.root or "-")
        shared.root = None
