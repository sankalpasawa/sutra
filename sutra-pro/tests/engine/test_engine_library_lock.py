"""P10 (work package E1, engine design 3.4 and risk 12; four writers since sync 6, D181): the template library's index is read, changed
and written back, so two runs storing different templates could lose one entry. `store`, `mark_used`, `note_version` and
`mark_run_template_used` now run inside an `fcntl.flock` on
`<library>/.lock`; a run that waits longer than `LOCK_WAIT_S` gets `LibraryBusy`, which the router turns into the generic
template. The race is reproduced with real processes; the 30 s wait is cut down to a fraction of a second here."""
import ast
import contextlib
import importlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ENGINE = "sutra_app.engine"
J2_MODULES = ("j2", "j2_agent", "j2_agent_models", "j2_agent_views", "j2_artifact_lib", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change",
              "j2_check", "j2_map", "j2_realization", "j2_rules", "j2_schema", "j2_send", "j2_story", "j2_studio", "j2_template_lib",
              "rehydrate")
BREW_LAB = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should "
            "see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for "
            "pickup. It should feel warm and modern and work well on a phone.")

# One writer process: waits for the start file, then stores COUNT templates with its own names and facts.
WRITER = textwrap.dedent('''
    import os, sys, time
    from sutra_app.engine import j2_template_lib as L
    prefix, count, start = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    while not os.path.exists(start):
        time.sleep(0.002)
    gen = L.generic("website", "Section")
    for i in range(count):
        need = L.make_need("website", "Section", "cafe", [f"{prefix} fact {i}"], f"Site {prefix}")
        data = L.specialise(gen, need, name=f"{prefix} template {i}")
        t = L.SpecialisedTemplate.model_validate({
            **data, "artifact": "website", "section": "Section", "kind": "specialised",
            "extends": L.generic_ref("website", "Section"),
            "made_by": {"run": prefix, "workflow": "w1", "atom": "a1", "agent": "test"},
            "context": {"business_type": "cafe", "facts_used": need["facts"], "fingerprint": need["fingerprint"]}})
        L.store(t)
    print("stored", count)
''')
# A holder process: takes the library lock and keeps it until its stdin closes.
HOLDER = textwrap.dedent('''
    import fcntl, os, sys
    os.makedirs(sys.argv[1], exist_ok=True)
    fd = os.open(os.path.join(sys.argv[1], ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    print("held", flush=True)
    sys.stdin.read()
''')


def child_env(library: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("J2_", "STUDIO_"))}
    env.update(J2_LIBRARY_DIR=str(library), PYTHONPATH=os.pathsep.join([str(REPO), *sys.path]))
    return env


@contextlib.contextmanager
def lock_held_by_another_process(library: Path):
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(library)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        yield
    finally:
        holder.stdin.close()
        holder.wait(timeout=10)


@pytest.fixture
def tpl(tmp_path, monkeypatch):
    """The vendored template library module pointed at a temp library, with a short lock wait."""
    for key in [k for k in os.environ if k.startswith(("J2_", "STUDIO_"))]:
        monkeypatch.delenv(key)
    monkeypatch.setenv("J2_LIBRARY_DIR", str(tmp_path / "library"))
    from sutra_app.engine import j2_template_lib
    monkeypatch.setattr(j2_template_lib, "LOCK_WAIT_S", 0.3)
    return j2_template_lib


def a_template(L, name="Cafe menu", fact="espresso"):
    need = L.make_need("website", "Section", "cafe", [fact], "Brew Lab")
    data = L.specialise(L.generic("website", "Section"), need, name=name)
    return L.SpecialisedTemplate.model_validate({
        **data, "artifact": "website", "section": "Section", "kind": "specialised", "extends": L.generic_ref("website", "Section"),
        "made_by": {"run": "r1", "workflow": "w1", "atom": "a1", "agent": "test"},
        "context": {"business_type": "cafe", "facts_used": need["facts"], "fingerprint": need["fingerprint"]}})


# ---- the race ------------------------------------------------------------------------------------------------------------
def test_two_processes_storing_different_templates_keep_both_index_entries(tmp_path):
    library, start = tmp_path / "library", tmp_path / "go"
    procs = [subprocess.Popen([sys.executable, "-c", WRITER, prefix, "6", str(start)], env=child_env(library),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for prefix in ("alpha", "beta")]
    time.sleep(0.5)             # both are in their wait loop: they start together
    start.write_text("go")
    outs = [p.communicate(timeout=120) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outs
    index = json.loads((library / "index.json").read_text())
    names = sorted(e["name"] for e in index["templates"])
    assert names == sorted(f"{p} template {i}" for p in ("alpha", "beta") for i in range(6))
    for entry in index["templates"]:
        assert [v["version"] for v in entry["versions"]] == [1]


def test_the_lock_file_lives_in_the_library_and_is_private(tpl, tmp_path):
    tpl.store(a_template(tpl))
    lock = tmp_path / "library" / ".lock"
    assert lock.is_file() and (lock.stat().st_mode & 0o777) == 0o600


def test_the_same_process_can_store_twice_in_a_row(tpl):
    t, version, created = tpl.store(a_template(tpl))
    again, version2, created2 = tpl.store(a_template(tpl))
    assert (version, created, version2, created2) == (1, True, 1, False), "the same content is the same version"
    changed, version3, created3 = tpl.store(a_template(tpl, fact="oat milk"))
    assert (version3, created3) == (2, True), "a change under the same name is the next version"


# ---- LibraryBusy ------------------------------------------------------------------------------------------------------
def test_store_gives_up_with_library_busy_after_the_wait(tpl, tmp_path):
    with lock_held_by_another_process(tmp_path / "library"):
        began = time.monotonic()
        with pytest.raises(tpl.LibraryBusy, match="locked by another run"):
            tpl.store(a_template(tpl))
        assert 0.25 <= time.monotonic() - began < 5
    assert tpl.index()["templates"] == [], "nothing was written without the lock"


def test_mark_used_gives_up_the_same_way(tpl, tmp_path):
    t, _, _ = tpl.store(a_template(tpl))
    with lock_held_by_another_process(tmp_path / "library"):
        with pytest.raises(tpl.LibraryBusy):
            tpl.mark_used(t, {"run": "r2", "workflow": "w1", "atom": "a1", "action": "reused"})
    assert tpl.index()["templates"][0]["versions"][0]["used_by"] == []


def test_a_wait_that_ends_in_time_succeeds(tpl, tmp_path, monkeypatch):
    monkeypatch.setattr(tpl, "LOCK_WAIT_S", 20.0)
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(tmp_path / "library")], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    import threading
    threading.Timer(0.4, holder.stdin.close).start()
    began = time.monotonic()
    t, version, created = tpl.store(a_template(tpl))
    assert created and version == 1 and 0.3 <= time.monotonic() - began < 10
    holder.wait(timeout=10)


def test_the_lock_is_released_when_the_write_fails(tpl, monkeypatch):
    real = tpl._save_index
    monkeypatch.setattr(tpl, "_save_index", lambda idx: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        tpl.store(a_template(tpl))
    monkeypatch.setattr(tpl, "_save_index", real)
    assert tpl.store(a_template(tpl, name="Another"))[2] is True, "the next writer was not locked out"


def test_library_busy_is_a_runtime_error_and_lock_wait_is_30_seconds():
    from sutra_app.engine import j2_template_lib
    assert issubclass(j2_template_lib.LibraryBusy, RuntimeError) and j2_template_lib.LOCK_WAIT_S == 30.0


# ---- sync 6 (D181): the two more writers, and no wrapper calls another wrapper ----------------------------------------------------
SEED = REPO / "sutra_app" / "engine" / "seed" / "library"
RUN_TEMPLATE = "iron-grove-fitness-prd-hld-lld-and-website"       # a row of the seed's `run_templates`

# Two writer processes of the sync 6 kind: one marks the run template used by many runs, the other adds provenance notes to the
# versions of one section (what `route`'s adapt path does), both on the same index at the same time.
USER = textwrap.dedent('''
    import os, sys, time
    from sutra_app.engine import j2_template_lib as L
    tid, count, start = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    while not os.path.exists(start):
        time.sleep(0.002)
    for i in range(count):
        L.mark_run_template_used(tid, {"run": f"run-{i}", "workflows": 1, "of": 20})
    print("marked", count)
''')
NOTER = textwrap.dedent('''
    import os, sys, time, types
    from sutra_app.engine import j2_template_lib as L
    count, start = int(sys.argv[1]), sys.argv[2]
    while not os.path.exists(start):
        time.sleep(0.002)
    rows = [(e, v) for e in L.index()["templates"] for v in e["versions"] if L.load(e["artifact"], L.slug(e["section"]), e["slug"], v["version"])][:count]
    for i, (e, v) in enumerate(rows):
        spec = L.load(e["artifact"], L.slug(e["section"]), e["slug"], v["version"])[0]
        t = types.SimpleNamespace(artifact=e["artifact"], section=e["section"], name=spec["name"], version=v["version"])
        L.note_version(t, noted_by=f"noter-{i}")
    print("noted", len(rows), flush=True)
    assert len(rows) == count, len(rows)
''')


def seeded_library(tmp_path) -> Path:
    library = tmp_path / "library"
    shutil.copytree(SEED, library)
    return library


def test_two_processes_use_one_run_template_and_adapt_a_section_at_once_without_losing_a_row(tmp_path):
    library, start = seeded_library(tmp_path), tmp_path / "go"
    before = json.loads((library / "index.json").read_text())
    used_before = next(r["used_by"] for r in before["run_templates"] if r["id"] == RUN_TEMPLATE)
    procs = [subprocess.Popen([sys.executable, "-c", code, *args, str(start)], env=child_env(library),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for code, args in ((USER, (RUN_TEMPLATE, "25")), (NOTER, ("25",)))]
    time.sleep(0.5)
    start.write_text("go")
    outs = [p.communicate(timeout=180) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outs
    after = json.loads((library / "index.json").read_text())
    assert next(r["used_by"] for r in after["run_templates"] if r["id"] == RUN_TEMPLATE) == used_before + 25
    template = json.loads((library / "run-templates" / RUN_TEMPLATE / "template.json").read_text())
    assert len(template["used_by"]) == used_before + 25
    noted = sorted(v["noted_by"] for e in after["templates"] for v in e["versions"] if "noted_by" in v)
    assert noted == sorted(f"noter-{i}" for i in range(25)), "every note reached its index row"
    assert len(after["templates"]) == len(before["templates"]) and len(after["run_templates"]) == len(before["run_templates"])


def test_note_version_and_mark_run_template_used_give_up_with_library_busy(tpl, tmp_path):
    shutil.copytree(SEED, tmp_path / "library")
    entry = tpl.index()["templates"][0]
    spec = tpl.load(entry["artifact"], tpl.slug(entry["section"]), entry["slug"], entry["versions"][0]["version"])[0]
    t = types.SimpleNamespace(artifact=entry["artifact"], section=entry["section"], name=spec["name"], version=entry["versions"][0]["version"])
    used = next(r["used_by"] for r in tpl.index()["run_templates"] if r["id"] == RUN_TEMPLATE)
    with lock_held_by_another_process(tmp_path / "library"):
        with pytest.raises(tpl.LibraryBusy):
            tpl.note_version(t, adapted_from="x")
        with pytest.raises(tpl.LibraryBusy):
            tpl.mark_run_template_used(RUN_TEMPLATE, {"run": "r9", "workflows": 1, "of": 20})
    row = tpl.index()["templates"][0]["versions"][0]
    assert row.get("adapted_from") != "x" and next(r["used_by"] for r in tpl.index()["run_templates"] if r["id"] == RUN_TEMPLATE) == used
    tpl.note_version(t, adapted_from="x")      # free again: the same call now works
    assert tpl.index()["templates"][0]["versions"][0]["adapted_from"] == "x"


def test_the_originals_are_kept_under_their_underscore_names_and_the_wrappers_take_the_lock():
    from sutra_app.engine import j2_template_lib as L
    for name in ("store", "mark_used", "note_version", "mark_run_template_used"):
        assert callable(getattr(L, name)) and callable(getattr(L, "_" + name)), name


def module_functions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def lock_takers(funcs):
    """Functions that take the library lock themselves: a `with _library_lock():` in the body."""
    out = set()
    for name, fn in funcs.items():
        for node in ast.walk(fn):
            if isinstance(node, ast.With) and any(isinstance(i.context_expr, ast.Call) and getattr(i.context_expr.func, "id", "") == "_library_lock"
                                                  for i in node.items):
                out.add(name)
    return out


def reachable(funcs, start):
    """Module functions called, directly or through other module functions, from `start` (by plain name)."""
    seen, todo = set(), [start]
    while todo:
        fn = funcs[todo.pop()]
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in funcs and node.func.id not in seen:
                seen.add(node.func.id)
                todo.append(node.func.id)
    return seen


def test_the_library_lock_is_taken_by_exactly_the_four_wrappers_and_never_nested():
    """The lock is a non-reentrant flock: a second acquire on a new descriptor of the same process waits LOCK_WAIT_S and then fails
    (D181). No function that takes it may reach one that takes it, and `collect`, which the host runs under the lock in its finish
    step, must reach none."""
    funcs = module_functions(REPO / "sutra_app" / "engine" / "j2_template_lib.py")
    takers = lock_takers(funcs)
    assert takers == {"store", "mark_used", "note_version", "mark_run_template_used"}
    for name in sorted(takers):
        assert not (reachable(funcs, name) & takers), f"{name} reaches a function that takes the library lock"
    assert "collect" in funcs and not (reachable(funcs, "collect") & takers)


def test_no_function_that_writes_the_index_runs_outside_the_lock_unless_it_is_a_developer_tool():
    """Every writer of the index (`_save_index`) is a wrapper's original, or a function listed here as a developer tool the app never
    calls (D181), or a function reached only from those: a new J2 writer that nobody wrapped fails here."""
    funcs = module_functions(REPO / "sutra_app" / "engine" / "j2_template_lib.py")
    takers = lock_takers(funcs)
    inside = set()
    for name in takers:
        inside |= reachable(funcs, name)
    writers = {n for n, fn in funcs.items() if any(isinstance(x, ast.Call) and getattr(x.func, "id", "") == "_save_index" for x in ast.walk(fn))}
    developer_tools = {"save_run_template", "move_versions", "collect"}      # `collect`: the host runs it under the lock (finish step)
    assert writers - inside - takers - developer_tools == set(), "an index writer that takes no lock"


# ---- the run falls back to the generic template ------------------------------------------------------------------------------
def fake_check(j2_check, html):
    st = j2_check.static_checks(html)
    return {"available": True, **st, "phone": {"width": 360, "overflow_px": 0}, "desktop": {"width": 1280, "overflow_px": 0},
            "js_errors": [], "design": {}, "form_results": [{"index": i + 1, "has_submit": True, "submitted": True, "invalid": [],
                                                           "errors_during": [], "ok": True} for i in range(st["forms"])]}


@contextlib.contextmanager
def fresh_j2(base: Path):
    from sutra_app.engine import llm
    package = importlib.import_module(ENGINE)
    saved = {name: (sys.modules.pop(f"{ENGINE}.{name}", None), package.__dict__.pop(name, None)) for name in J2_MODULES}
    with pytest.MonkeyPatch.context() as mp:
        for name in list(os.environ):
            if name.startswith(("J2_", "STUDIO_")):
                mp.delenv(name)
        for key, value in {"STUDIO_MOCK": "1", "J2_MEMORY": "0", "J2_REALIZATION": "0", "J2_TEMPLATE_LIBRARY": "1", "J2_BUDGET": "1400",
                           "J2_MEMORY_FILE": base / "lessons.jsonl", "J2_PLAYBOOK_FILE": base / "playbooks.jsonl",
                           "J2_RUNS_DIR": base / "runs", "J2_LIBRARY_DIR": base / "library"}.items():
            mp.setenv(key, str(value))
        mp.setattr(llm, "MOCK", True)
        try:
            mod = importlib.import_module(f"{ENGINE}.j2")
            mod.j2_check.find_chrome = lambda: None
            mod.j2_check.tap_targets = lambda html, selector, min_px=44: {"available": True, "roots": 1, "checked": 0,
                                                                          "small_count": 0, "small": []}
            mod.j2_check.check = lambda html: fake_check(mod.j2_check, html)
            yield mod
        finally:
            for name, (old, attr) in saved.items():
                sys.modules.pop(f"{ENGINE}.{name}", None)
                package.__dict__.pop(name, None)
                if old is not None:
                    sys.modules[f"{ENGINE}.{name}"] = old
                if attr is not None:
                    package.__dict__[name] = attr


def run_brew_lab(j2, base: Path):
    """A mock Brew Lab run to its end; the one conflict question is answered with the simpler option, as J2's own tests do."""
    folder = base / "runs" / "j2-20261104-100001-7f3a"
    folder.mkdir(parents=True)
    run = j2.J2Run(run_dir=folder)
    text = BREW_LAB
    for _ in range(4):
        assert run.user_says(text) is True
        deadline = time.time() + 60
        while run.status != "waiting":
            assert time.time() < deadline, "the run did not stop"
            time.sleep(0.003)
        if not run.paused:
            break
        text = "Option 2" if run.paused["kind"] == "conflict" else "1"
    return run, json.loads((folder / "templates.json").read_text())


def test_a_run_that_cannot_get_the_lock_falls_back_to_the_generic_template(tmp_path, llm_reset):
    llm_reset.configure(mock=True)
    with fresh_j2(tmp_path) as j2:
        j2.j2_template_lib.LOCK_WAIT_S = 0.2
        with lock_held_by_another_process(tmp_path / "library"):
            run, templates = run_brew_lab(j2, tmp_path)
        assert run.outcome.startswith("Done"), run.outcome
    decisions = templates["decisions"]
    assert decisions and {d["action"] for d in decisions} == {"generic"}
    assert any("LibraryBusy" in d["reason"] for d in decisions), decisions
    assert not (tmp_path / "library" / "index.json").exists() or json.loads(
        (tmp_path / "library" / "index.json").read_text())["templates"] == []


def test_the_same_run_creates_its_templates_when_the_library_is_free(tmp_path, llm_reset):
    llm_reset.configure(mock=True)
    with fresh_j2(tmp_path) as j2:
        run, templates = run_brew_lab(j2, tmp_path)
        assert run.outcome.startswith("Done"), run.outcome
    assert "created" in {d["action"] for d in templates["decisions"]}
    assert json.loads((tmp_path / "library" / "index.json").read_text())["templates"]
