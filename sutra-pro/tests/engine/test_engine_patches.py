"""The patches of the vendored J2 (work package E1, engine design 3.4): P2 role-file folder, P3 explicit run folder and id,
P4 non-blocking user_says and apply_override, P5 explicit-path memory and saved-run functions, P7 tagged model calls,
P8 hooks, P9 the system addendum, P14 `single` with no type, P16 Decide for me's settings file, P17 the local type store and
P18 host type registration (sync 5), and since sync 6 P19 (the reviewer switch) and the P7, P8 and P9 anchors at the new pin. J2 runs in mock mode with its Chrome checks faked (as J2's own `--fast` flow does), so a
whole Brew Lab run takes about a tenth of a second. P1 (imports) and P10 (the library lock) are in test_engine_vendor.py and
test_engine_library_lock.py, P11 (rehydrate) in test_engine_rehydrate.py."""
import contextlib
import hashlib
import importlib
import itertools
import math
import json
import os
import re
import shlex
import shutil
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ENGINE = "sutra_app.engine"
J2_MODULES = ("j2", "j2_agent", "j2_agent_models", "j2_agent_views", "j2_artifact_lib", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change",
              "j2_check", "j2_map", "j2_realization", "j2_rules", "j2_schema", "j2_send", "j2_story", "j2_studio", "j2_template_lib",
              "j2_types", "rehydrate")
BREW_LAB = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should "
            "see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for "
            "pickup. It should feel warm and modern and work well on a phone. Include a section about our beans and the "
            "farms they come from, and a simple loyalty-card explainer (buy 9, get the 10th free).")
VAGUE = ["a website for my cafe",
         "It's called Little Fig, in Koramangala, Bengaluru. Visitors should see our menu with prices, opening hours and "
         "where to find us. Cozy and simple, and it must work on phones.",
         "Option 2: skip the stories, keep the reserve for fixes."]
BASE_RUN = "j2-20261104-100004-7f3a"


# ---- a fresh import of the vendored J2 (it reads its flags and paths when it is imported) ----------------------------
def fake_check(j2_check, html):
    """J2's --fast stub: the render check without a browser (static checks, no overflow, no script errors)."""
    st = j2_check.static_checks(html)
    return {"available": True, **st, "phone": {"width": 360, "overflow_px": 0}, "desktop": {"width": 1280, "overflow_px": 0},
            "js_errors": [], "design": {}, "form_results": [{"index": i + 1, "has_submit": True, "submitted": True, "invalid": [],
                                                           "errors_during": [], "ok": True} for i in range(st["forms"])]}


@contextlib.contextmanager
def fresh_j2(base: Path, **env):
    """Import the vendored J2 anew in mock mode with its paths under `base` and extra environment variables `env`; put the
    modules (and the environment) back afterwards."""
    from sutra_app.engine import llm
    package = importlib.import_module(ENGINE)
    # a submodule is found twice: in sys.modules and as an attribute of the package (`from . import x` trusts the attribute)
    saved = {name: (sys.modules.pop(f"{ENGINE}.{name}", None), package.__dict__.pop(name, None)) for name in J2_MODULES}
    with pytest.MonkeyPatch.context() as mp:
        for name in list(os.environ):
            if name.startswith(("J2_", "STUDIO_")):
                mp.delenv(name)
        for key, value in {"STUDIO_MOCK": "1", "J2_MEMORY": "0", "J2_REALIZATION": "0", "J2_MEMORY_FILE": str(base / "lessons.jsonl"),
                           "J2_PLAYBOOK_FILE": str(base / "playbooks.jsonl"), "J2_RUNS_DIR": str(base / "runs"),
                           "J2_LIBRARY_DIR": str(base / "library"), **env}.items():
            mp.setenv(key, str(value))
        mp.setattr(llm, "MOCK", True)               # J2 reads llm.MOCK when it is imported
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


@pytest.fixture(scope="module")
def j2(tmp_path_factory):
    with fresh_j2(tmp_path_factory.mktemp("j2-env")) as mod:
        yield mod


@pytest.fixture(autouse=True)
def mock_mode(llm_reset):
    llm_reset.configure(mock=True)
    return llm_reset


@pytest.fixture
def make_run(j2, tmp_path):
    counter = itertools.count(1)

    def make(**kw):
        return j2.J2Run(run_dir=tmp_path / "runs" / f"j2-20261104-1000{next(counter):02d}-7f3a", **kw)
    return make


def say(run, text, timeout=60.0):
    assert run.user_says(text) is True
    deadline = time.time() + timeout
    while run.status != "waiting":
        assert time.time() < deadline, "the run did not stop"
        time.sleep(0.003)


def hooks_module():
    from sutra_app.engine import hooks
    return hooks


def recorder(run_getter=None):
    hooks = hooks_module()

    class Recorder(hooks.NullHooks):
        """Keeps every hook call as (name, *args)."""

        def __init__(self):
            self.calls, self.run, self.addendum = [], None, ""

        def run_status(self, snap):
            self.calls.append(("run_status", snap))

        def turn_started(self, t):
            self.calls.append(("turn_started", t))

        def turn_finished(self, t, o):
            self.calls.append(("turn_finished", t, o))

        def call_finished(self, c):
            self.calls.append(("call_finished", c))

        def message_posted(self, m, questions=None):
            self.calls.append(("message_posted", m, questions, bool(self.run and self.run.paused)))

        def record_saved(self, name, data):
            self.calls.append(("record_saved", name, data))
            return []

        def run_error(self, code, message):
            self.calls.append(("run_error", code, message))

        def system_addendum(self, fn):
            self.calls.append(("system_addendum", fn))
            return self.addendum

        def of(self, name):
            return [c[1:] for c in self.calls if c[0] == name]
    return Recorder()


def captured_port():
    """A ScriptedPort that remembers every request."""
    from sutra_app.engine.llm import ScriptedPort

    class Capture(ScriptedPort):
        def __init__(self):
            super().__init__()
            self.requests = []

        def complete(self, req, on_progress=None):
            self.requests.append(req)
            return super().complete(req, on_progress)
    return Capture()


def base_tag():
    from sutra_app.engine.port import CallTag
    return CallTag(run_id=BASE_RUN, dept_id="web", task_id="tsk_a1b2c3d4e5f6")


def with_timeout(fn, seconds=3.0):
    """fn() on a thread: (finished, result). A patch that blocks must fail a test, not hang it."""
    box = {}
    thread = threading.Thread(target=lambda: box.setdefault("v", fn()), daemon=True)
    thread.start()
    thread.join(seconds)
    return (not thread.is_alive()), box.get("v")


# ---- the runs --------------------------------------------------------------------------------------------------------
def test_a_mock_brew_lab_run_reaches_done_in_process(j2, make_run):
    run = make_run()
    say(run, BREW_LAB)
    assert run.outcome.startswith("Done: the site is workable"), run.outcome
    summary = json.loads((Path(run.dir) / "summary.json").read_text())
    assert summary["status"] == "done" and summary["mock"] is True
    assert len(run.workflows) >= 4 and run.sites and run.calls >= 20
    assert (Path(run.dir) / "calls.jsonl").is_file() and (Path(run.dir) / "chat.jsonl").is_file()


# ---- P3: the host names the run folder and id --------------------------------------------------------------------
def test_p3_the_host_names_the_run_folder_and_id(j2, tmp_path):
    run = j2.J2Run(run_dir=tmp_path / "runs" / BASE_RUN, run_id="host-id")
    assert run.dir == str(tmp_path / "runs" / BASE_RUN) and run.run_id == "host-id"
    assert not (tmp_path / "runs").exists(), "constructing a run writes nothing"


def test_p3_without_an_id_the_run_id_is_the_folder_name_without_j2(j2, tmp_path):
    assert j2.J2Run(run_dir=tmp_path / BASE_RUN).run_id == BASE_RUN[3:]


def test_p3_an_id_without_a_folder_is_refused(j2):
    with pytest.raises(ValueError, match="run_id needs run_dir"):
        j2.J2Run(run_id="host-id")


def test_p3_a_relative_folder_is_made_absolute(j2, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert j2.J2Run(run_dir="runs/j2-x").dir == str(tmp_path / "runs" / "j2-x")


def test_p3_without_arguments_j2_makes_its_timestamp_folder_and_has_no_hooks(j2):
    run = j2.J2Run()
    assert os.path.dirname(run.dir) == j2.RUNS_DIR and os.path.basename(run.dir).startswith("j2-")
    assert run.run_id == os.path.basename(run.dir)[3:]
    assert type(run.hooks) is hooks_module().NullHooks


def test_p3_only_the_first_reset_takes_the_hosts_folder(j2, tmp_path):
    run = j2.J2Run(run_dir=tmp_path / BASE_RUN)
    run.reset()
    assert os.path.dirname(run.dir) == j2.RUNS_DIR, "a later reset is J2's own: a new timestamp folder"


# ---- P4: user_says and apply_override never wait for the run --------------------------------------------------------
def test_p4_user_says_returns_false_at_once_while_the_run_holds_the_lock(j2, make_run):
    run = make_run()
    run.lock.acquire()
    try:
        started = time.time()
        done, result = with_timeout(lambda: run.user_says("hello"))
        assert done and result is False and time.time() - started < 1.0
        assert run.chat == [] and run.status == "idle", "a refused line posts nothing and starts nothing"
    finally:
        run.lock.release()


def test_p4_user_says_is_false_while_running_and_releases_the_lock(j2, make_run):
    run = make_run()
    run.status = "running"
    assert run.user_says("hello") is False
    assert run.lock.acquire(blocking=False), "the lock is free again"
    run.lock.release()


def test_p4_a_normal_message_still_starts_the_run_and_frees_the_lock(j2, make_run):
    run = make_run()
    say(run, BREW_LAB)
    assert run.lock.acquire(blocking=False)
    run.lock.release()


def test_p4_apply_override_applies_the_command_without_a_key(j2, make_run):
    run = make_run()
    say(run, BREW_LAB)
    before = run.budget
    assert run.apply_override("budget +5") is True
    assert run.budget == before + 5 and run.raises[-1]["override"] is True
    note = run.chat[-1]
    assert note["who"] == "system" and note["text"].startswith("Owner override applied: budget +5") and note["override"]


def test_p4_apply_override_ship_and_a_bad_command(j2, make_run):
    run = make_run()
    say(run, BREW_LAB)
    assert run.apply_override("what") is True
    assert run.chat[-1]["text"].startswith("Owner override not applied")
    assert run.apply_override("ship") is True and run.chat[-1]["text"].startswith("Owner override applied: ship")


def test_p4_apply_override_is_false_while_locked_or_running(j2, make_run):
    run = make_run()
    run.lock.acquire()
    try:
        done, result = with_timeout(lambda: run.apply_override("budget +5"))
        assert done and result is False
    finally:
        run.lock.release()
    run.status = "running"
    assert run.apply_override("budget +5") is False and run.budget == j2.BUDGET


def test_p4_the_override_key_in_the_environment_is_still_j2s_own(j2, make_run, monkeypatch):
    run = make_run()
    say(run, BREW_LAB)
    monkeypatch.setenv("J2_OVERRIDE_KEY", "sesame")
    before, n = run.budget, len(run.chat)
    assert run.user_says("sesame budget +3") is True
    assert run.budget == before + 3 and len(run.chat) == n + 1, "the key is never posted"


# ---- P5: explicit paths, the old constants as defaults --------------------------------------------------------------
def test_p5_lessons_and_playbooks_take_a_path(j2, tmp_path, monkeypatch):
    monkeypatch.setenv("J2_MEMORY", "1")
    lessons, playbooks = tmp_path / "other" / "lessons.jsonl", tmp_path / "other" / "playbooks.jsonl"
    j2.save_lesson({"id": "L-1", "fix": "a"}, lessons)
    j2.save_lesson({"id": "L-2", "fix": "b"}, lessons)
    assert [x["id"] for x in j2.load_lessons(lessons)] == ["L-1", "L-2"] and j2.load_lessons() == []
    assert j2.load_lessons(tmp_path / "missing.jsonl") == []
    assert j2.clear_lessons(lessons) == 2 and not lessons.exists() and j2.clear_lessons(lessons) == 0
    j2.save_playbook({"id": "P-1", "v": 1}, playbooks)
    j2.save_playbook({"id": "P-2", "v": 1}, playbooks)
    j2.save_playbook({"id": "P-1", "v": 2}, playbooks)
    assert [(x["id"], x["v"]) for x in j2.load_playbooks(playbooks)] == [("P-2", 1), ("P-1", 2)], "a playbook replaces its own id"
    assert j2.load_playbooks() == [] and j2.clear_playbooks(playbooks) == 2 and not playbooks.exists()


def test_p5_without_a_path_the_old_constants_are_used(j2, monkeypatch):
    monkeypatch.setenv("J2_MEMORY", "1")
    j2.save_lesson({"id": "L-9"})
    j2.save_playbook({"id": "P-9"})
    try:
        assert os.path.exists(j2.MEMORY_FILE) and [x["id"] for x in j2.load_lessons()] == ["L-9"]
        assert [x["id"] for x in j2.load_playbooks(j2.PLAYBOOK_FILE)] == ["P-9"]
    finally:
        assert j2.clear_lessons() == 1 and j2.clear_playbooks() == 1


def test_p5_saved_runs_are_read_from_the_runs_folder_given(j2, make_run, tmp_path):
    run = make_run()
    say(run, BREW_LAB)
    runs, name = os.path.dirname(run.dir), os.path.basename(run.dir)
    assert j2.saved_dir(name) is None and j2.saved_dir(name, runs) == run.dir
    assert j2.saved_dir("../" + name, runs) is None and j2.saved_dir("not-a-run", runs) is None
    assert [r["id"] for r in j2.list_runs(runs_dir=runs)] == [name] and j2.list_runs(runs_dir=str(tmp_path / "none")) == []
    snap = j2.saved_snapshot_dir(run.dir, name)
    assert snap["saved"] == name and snap["status"] == "saved" and snap["total"] == len(run.chat)
    assert j2.saved_snapshot_dir(run.dir, name, since=len(run.chat) - 1)["chat"] == run.chat[-1:]
    assert j2.saved_snapshot(name) is None, "saved_snapshot still looks in J2_RUNS_DIR"


def test_p5_saved_snapshot_reads_through_saved_snapshot_dir(j2, tmp_path):
    name = "j2-20261104-100004-9999"
    target = Path(j2.RUNS_DIR) / name
    run = j2.J2Run(run_dir=target)
    say(run, BREW_LAB)
    assert j2.saved_snapshot(name) == j2.saved_snapshot_dir(str(target), name)
    assert j2.list_runs()[0]["id"] == name and j2.saved_dir(name) == str(target)


# ---- P2: the role-file folder ---------------------------------------------------------------------------------------
def test_p2_the_role_files_default_to_the_package_copy(j2):
    package = Path(j2.__file__).parent / "agents" / "j2"
    assert Path(j2.J2_DIR) == package and Path(j2.j2_realization.AGENTS) == package
    assert (package / "identity.md").is_file() and "Identity" in j2.system_prompt("identity", "{}")


def test_p2_j2_agents_dir_replaces_the_folder(tmp_path):
    custom = tmp_path / "roles"
    custom.mkdir()
    package = Path(importlib.import_module(ENGINE).__file__).parent / "agents" / "j2"
    for f in package.iterdir():
        text = f.read_text(encoding="utf-8")
        (custom / f.name).write_text(text + ("\nCUSTOM-MARKER-X\n" if f.name == "identity.md" else ""), encoding="utf-8")
    with fresh_j2(tmp_path / "env", J2_AGENTS_DIR=custom) as mod:
        assert mod.J2_DIR == str(custom) and mod.j2_realization.AGENTS == str(custom)
        assert mod.j2_types.AGENTS_DIR == str(custom), "P2, third edit: a page type's builder is a role file"
        assert os.path.join(mod.j2_types.AGENTS_DIR, mod.j2_types.load("website")["builder"]) == str(custom / "builder.md")
        assert "CUSTOM-MARKER-X" in mod.system_prompt("identity", "{}")
        assert "CUSTOM-MARKER-X" not in mod.system_prompt("audit", "{}")


# ---- P7: every model call is tagged ---------------------------------------------------------------------------------
def tagged_run(j2, make_run, mock_mode, text=BREW_LAB, **kw):
    port = captured_port()
    mock_mode.configure(port, mock=True, base_tag=base_tag())
    run = make_run(**kw)
    say(run, text)
    settle(run)
    return run, port


def test_p7_every_agent_call_carries_its_function_step_and_the_hosts_base_tag(j2, make_run, mock_mode):
    run, port = tagged_run(j2, make_run, mock_mode)
    logged = [json.loads(line) for line in (Path(run.dir) / "calls.jsonl").read_text().splitlines()]
    agent = [r for r in port.requests if r.tag.purpose == "agent_turn"]
    assert len(agent) == len(logged) > 20
    for req, rec in zip(agent, logged):
        t = req.tag
        assert (t.run_id, t.dept_id, t.task_id) == (BASE_RUN, "web", "tsk_a1b2c3d4e5f6")
        assert t.function == rec["fn"] and t.step == rec["step"] and t.cycle == rec["cycle"] and t.call_no == rec["id"]
        assert t.stage == "website" and req.allowance is None, "the engine sends no allowance (S1-contracts-06)"
    assert {r.tag.function for r in agent} >= {"identity", "adaptation", "priority", "coordination", "audit", "W-1"}


def test_p7_builder_calls_carry_their_role_and_atom(j2, make_run, mock_mode):
    run, port = tagged_run(j2, make_run, mock_mode)
    built = [r.tag for r in port.requests if r.tag.function.startswith("W-")]
    assert built and all(t.role == "builder" and t.atom and t.atom.startswith(t.function + ".a") for t in built)
    others = [r.tag for r in port.requests if not r.tag.function.startswith("W-")]
    assert all(t.role is None and t.atom is None for t in others if t.purpose == "agent_turn")


def test_p7_the_reviewer_and_the_summariser_are_tagged_and_unlogged(j2, make_run, mock_mode, monkeypatch):
    monkeypatch.setattr(j2, "CHAT_FULL_CHARS", 300)          # a short limit: the chat is summarised
    run, port = tagged_run(j2, make_run, mock_mode)
    by = {(r.tag.function, r.tag.purpose): r.tag for r in port.requests}
    assert ("reviewer", "review") in by and ("summariser", "summary") in by
    assert by[("reviewer", "review")].call_no == 0 and by[("summariser", "summary")].call_no == 0, "J2 does not log them"
    assert by[("reviewer", "review")].run_id == BASE_RUN


def test_p7_the_planner_and_the_judge_inherit_the_function_of_the_turn(j2, make_run, mock_mode, monkeypatch):
    monkeypatch.setenv("J2_REALIZATION", "1")
    run, port = tagged_run(j2, make_run, mock_mode)
    helpers = [r.tag for r in port.requests if r.tag.role in ("planner", "judge")]
    assert {t.role for t in helpers} == {"planner", "judge"}
    for t in helpers:
        assert t.function == "adaptation" and t.purpose == ("plan" if t.role == "planner" else "judge")
        assert t.step == 2 and t.run_id == BASE_RUN


def test_p7_a_session_call_in_a_change_turn_has_the_purpose_change(j2, mock_mode):
    port = captured_port()
    mock_mode.configure(port, mock=True)
    session = j2.j2_realization.Session(log=lambda *a: None)
    session.ask("judge", "s", "u", lambda: "{}")
    with mock_mode.tagged(purpose="change"):
        session.ask("adaptation", "s", "u", lambda: "{}")
    assert [(r.tag.role, r.tag.purpose) for r in port.requests] == [("judge", "judge"), ("planner", "change")]


def test_p7_the_template_generator_is_tagged(j2, make_run, mock_mode, monkeypatch):
    monkeypatch.setenv("J2_TEMPLATE_LIBRARY", "1")
    run, port = tagged_run(j2, make_run, mock_mode)
    tags = [r.tag for r in port.requests if r.tag.purpose == "template"]
    assert tags and all(t.function == "template" and t.call_no == 0 for t in tags)


def test_p7_the_turn_tag_does_not_leak_out_of_the_turn(j2, make_run, mock_mode):
    mock_mode.configure(captured_port(), mock=True, base_tag=base_tag())
    run = make_run()
    say(run, BREW_LAB)
    assert mock_mode.current_tag() == base_tag()


# ---- P8: hooks --------------------------------------------------------------------------------------------------------
def settle(run):
    """J2 (since sync 6) writes report.json, report.md and artifacts.json after the run is `waiting`, from the reviewer's thread
    (D179): a test that reads the folder or the hook calls waits for it, as the host does."""
    thread = getattr(run, "review_thread", None)
    if thread is not None:
        thread.join(30)
        assert not thread.is_alive()


def hooked_run(j2, make_run, mock_mode, texts=(BREW_LAB,), **kw):
    mock_mode.configure(mock=True, base_tag=base_tag())
    rec = recorder()
    run = make_run(hooks=rec, **kw)
    rec.run = run
    for text in texts:
        say(run, text)
    settle(run)
    return run, rec


def test_p8_a_hooked_run_pairs_every_turn_start_with_its_finish(j2, make_run, mock_mode):
    run, rec = hooked_run(j2, make_run, mock_mode)
    names = [c[0] for c in rec.calls]
    assert names[:4] == ["message_posted", "run_status", "record_saved", "turn_started"]
    last_status = max(i for i, n in enumerate(names) if n == "run_status")
    late = [c[1] for c in rec.calls[last_status + 1:]]
    assert late and set(late) <= {"report.json", "artifacts.json"} and all(n == "record_saved" for n in names[last_status + 1:]), \
        "after the run end hook only the reviewer's thread writes (the host joins it, D179)"
    assert rec.calls[2][1] == "deliverables.json", "J2's planner call of _plan_stages (sync 5) saves its answer before the first turn"
    open_turn, numbers = None, []
    for c in rec.calls:
        if c[0] == "turn_started":
            assert open_turn is None, "a turn started inside another"
            open_turn = c[1].turn_no
            numbers.append(open_turn)
        elif c[0] == "turn_finished":
            assert c[1].turn_no == open_turn
            open_turn = None
    assert open_turn is None and numbers == list(range(1, run.turn_no + 1)) and run.turn_no > 20


def test_p8_calls_happen_inside_turns_and_every_message_is_reported_once(j2, make_run, mock_mode):
    run, rec = hooked_run(j2, make_run, mock_mode)
    inside = False
    for c in rec.calls:
        inside = {"turn_started": True, "turn_finished": False}.get(c[0], inside)
        if c[0] == "call_finished":
            assert inside, "a call finished outside a turn"
    posted = [c[1]["id"] for c in rec.calls if c[0] == "message_posted"]
    assert posted == [m["id"] for m in run.chat]
    assert [c[1].call_no for c in rec.calls if c[0] == "call_finished"] == [r["id"] for r in run.call_log]


def test_p8_the_turn_info_is_complete(j2, make_run, mock_mode):
    run, rec = hooked_run(j2, make_run, mock_mode)
    first = rec.of("turn_started")[0][0]
    assert (first.run_id, first.dept_id, first.task_id) == (BASE_RUN, "web", "tsk_a1b2c3d4e5f6")
    assert (first.turn_no, first.function, first.kind, first.step, first.cycle, first.stage) == (1, "identity", "intake", 1, 0, "website")
    assert first.step_label == "J2.a Enough information to work?" and first.task == "intake"
    assert first.context and all(isinstance(p, tuple) and len(p) == 2 for p in first.context)
    assert [label for label, _ in first.context] == ["chat"]
    later = rec.of("turn_started")[8][0]          # Priority checks an envelope: its context has the ledger and workflows
    assert later.function == "priority" and later.kind == "envelope"
    assert {"charter", "ledger", "workflows"} <= {label for label, _ in later.context} and "task" not in {l for l, _ in later.context}
    why = next(t for (t,) in rec.of("turn_started") if run.turn_no and t.task != (t.kind or ""))
    assert why.task and why.task != why.kind, "the handoff's why is the task"


def test_p8_a_charter_change_turn_is_adaptations(j2, make_run, mock_mode):
    mock_mode.configure(mock=True, base_tag=base_tag())
    rec = recorder()
    run = make_run(hooks=rec)
    rec.run = run
    run.goal, run.cycle = {"done_when": ["a", "b", "c"]}, 1
    seen = {}
    run._turn_change = lambda h: seen.update(tag=mock_mode.current_tag()) or run._handoff("coordination", kind="schedule")
    run._handoff("change", change={}, start={}, new_cycle=False)
    run._dispatch_turn()
    t = rec.of("turn_started")[0][0]
    assert (t.function, t.kind, t.step) == ("adaptation", "change", 2)
    assert (seen["tag"].function, seen["tag"].purpose, seen["tag"].step) == ("adaptation", "change", 2)


def test_p8_the_step_told_at_the_start_is_the_step_of_the_first_call(j2, make_run, mock_mode):
    wrong = []
    for texts in ((BREW_LAB,), VAGUE + ["Add a section for visiting hours"]):
        run, rec = hooked_run(j2, make_run, mock_mode, texts)
        started = None
        for c in rec.calls:
            if c[0] == "turn_started":
                started = [c[1], False]
            elif c[0] == "call_finished" and started and not started[1]:
                started[1] = True
                if c[1].step != started[0].step:
                    wrong.append((started[0].function, started[0].kind, started[0].step, c[1].step))
    assert wrong == []


def test_p8_turn_step_covers_every_dispatch_kind(j2):
    step = j2.turn_step
    assert [step("identity", k, 5) for k in ("intake", "resolve", "question", "ruling_budget", "approval", "stage_decision",
                                              "requester_answered", "limit", "audit", "whatever")] == [1, 4, 4, 4, 6, 8, 8, 8, 8, 4]
    assert [step("adaptation", k, 5) for k in ("propose", "respond", "atom_failed", "dispute", "change")] == [2] * 5
    assert [step("priority", k, 5) for k in ("proposal", "ruling", "envelope", "dispute")] == [3, 3, 6, 5]
    assert [step("coordination", k, 5) for k in ("schedule", "dispute")] == [6, 5]
    assert [step("audit", k, 5) for k in ("audit", "dispute")] == [7, 5]
    assert step("identity", "send_confirm", 5) == 5 and step("W-3", "build", 1) == 6


def test_p8_the_outcome_of_an_ordinary_turn(j2, make_run, mock_mode):
    run, rec = hooked_run(j2, make_run, mock_mode)
    t, o = rec.of("turn_finished")[0]
    assert t.turn_no == 1 and o.result == "ok" and o.next == "adaptation"
    assert o.messages == [m["id"] for m in run.chat[1:1 + len(o.messages)]] and len(o.messages) >= 2, "message 1 is the owner's"
    assert o.calls == [1] and o.notes == []
    last = rec.of("turn_finished")[-1][1]
    assert last.next is None, "the last turn hands over to no one"
    assert "redirected" in {o.result for _, o in rec.of("turn_finished")}


def test_p8_a_turn_that_asks_the_requester_ends_paused_and_the_hook_hears_the_question_once(j2, make_run, mock_mode):
    run, rec = hooked_run(j2, make_run, mock_mode, VAGUE[:1])
    assert run.paused and run.paused["kind"] == "info"
    t, o = rec.of("turn_finished")[-1]
    assert (t.function, t.kind, o.result, o.next) == ("identity", "intake", "paused", None)
    asked = [c for c in rec.calls if c[0] == "message_posted" and c[1].get("act") == "ASK_REQUESTER"]
    assert len(asked) == 1, "post() leaves the question to _ask_user: told once"
    _, message, questions, paused_when_told = asked[0]
    assert questions == run.paused["questions"] and message["id"] == run.paused["msg"] and paused_when_told is True
    assert message["id"] in o.messages
    assert [c[1]["id"] for c in rec.calls if c[0] == "message_posted"] == [m["id"] for m in run.chat]


def test_p8_run_status_reports_running_and_waiting(j2, make_run, mock_mode):
    run, rec = hooked_run(j2, make_run, mock_mode, VAGUE[:1])
    states = [(s["status"], s["paused"]["kind"] if s["paused"] else None) for (s,) in rec.of("run_status")]
    assert states == [("running", None), ("waiting", "info")]
    snap = rec.of("run_status")[-1][0]
    assert set(snap) == {"status", "done", "turn", "step", "cycle", "calls", "error", "outcome", "paused"}
    assert snap["done"] is True and snap["outcome"].startswith("Paused") and snap["calls"] == run.calls
    run2, rec2 = hooked_run(j2, make_run, mock_mode)
    final = rec2.of("run_status")[-1][0]
    assert final["status"] == "waiting" and final["paused"] is None and final["outcome"].startswith("Done")


def test_p8_record_saved_gets_the_name_and_the_data_that_was_written(j2, make_run, mock_mode):
    run, rec = hooked_run(j2, make_run, mock_mode)
    saved = {name: data for name, data in rec.of("record_saved")}
    assert {"goal.json", "workflows.json", "summary.json", "sections.json", "audits.json"} <= set(saved)
    assert saved["goal.json"] == json.loads((Path(run.dir) / "goal.json").read_text())
    assert saved["summary.json"]["status"] == "done"


def test_p8_call_finished_describes_the_call(j2, make_run, mock_mode):
    mock_mode.bind_atom("a-1234567890-01")
    run, rec = hooked_run(j2, make_run, mock_mode)
    first = rec.of("call_finished")[0][0]
    assert (first.call_no, first.function, first.step, first.purpose, first.stage) == (1, "identity", 1, "agent_turn", "website")
    assert first.reply["reason"] and first.reason == first.reply["reason"] == run.call_log[0]["reason"]
    assert "reason" not in run.call_log[0]["reply"] and set(first.reply) - {"reason"} == set(run.call_log[0]["reply"])
    assert first.inputs == run.call_log[0]["inputs"] and first.model is None and first.tokens is None
    assert first.atom == "a-1234567890-01", "a call outside a builder is charged to the bound atom"
    built = next(c for (c,) in rec.of("call_finished") if c.function == "W-1")
    assert built.atom == "W-1.a1", "a builder's own atom id wins over the binding"
    first.reply["enough"] = "mutated"
    assert run.call_log[0]["reply"]["enough"] is True, "the hook got a copy"


def test_p8_calls_jsonl_gains_provider_and_usd(j2, make_run, mock_mode, monkeypatch):
    run = make_run()
    rec = run._log_call("identity", "task", "sys", "usr", "{}", {"say": "x", "reason": "r"}, 0.5)
    assert rec["provider"] is None and rec["usd"] is None, "mock mode leaves them empty"
    monkeypatch.setattr(mock_mode, "MOCK", False)
    mock_mode.LAST_META.update(provider="claude", usd=0.0123, model="sonnet", input_tokens=5, output_tokens=7)
    rec = run._log_call("identity", "task", "sys", "usr", "{}", {"say": "x", "reason": "r"}, 0.5)
    assert (rec["provider"], rec["usd"], rec["model"], rec["tokens"]) == ("claude", 0.0123, "sonnet", {"input": 5, "output": 7})
    stored = json.loads((Path(run.dir) / "calls.jsonl").read_text().splitlines()[-1])
    assert stored["provider"] == "claude" and stored["usd"] == 0.0123
    mock_mode.LAST_META.clear()


def test_p8_a_turn_that_raises_still_finishes_and_the_error_goes_on(j2, make_run, mock_mode):
    rec = recorder()
    run = make_run(hooks=rec)
    run.goal, run.cycle = {"done_when": ["a", "b", "c"]}, 1
    run._handoff("audit", kind="audit")

    def boom(h):
        raise RuntimeError("the model is gone")
    run._turn_audit = boom
    with pytest.raises(RuntimeError, match="the model is gone"):
        run._dispatch_turn()
    t, o = rec.of("turn_finished")[0]
    assert (t.function, o.result) == ("audit", "error") and o.notes[0] == "RuntimeError: the model is gone"


def test_p8_a_redirected_turn_is_reported_with_its_notes(j2, make_run, mock_mode):
    rec = recorder()
    run = make_run(hooks=rec)
    run.goal, run.cycle = {"done_when": ["a", "b", "c"]}, 1
    run._handoff("audit", kind="audit")
    run._turn_audit = lambda h: run._say("audit", "@Requester can you send the phone number?", "adaptation")
    run._dispatch_turn()
    t, o = rec.of("turn_finished")[0]
    assert o.result == "redirected" and o.next == "audit" and any(n.startswith("redirect:") for n in o.notes)
    assert len(o.messages) == 2 and o.calls == []


def test_p8_hooks_that_raise_never_reach_the_run(j2, make_run, mock_mode, capsys):
    hooks = hooks_module()

    class Broken(hooks.NullHooks):
        def __getattribute__(self, name):
            if name in ("message_posted", "turn_started", "turn_finished", "call_finished", "record_saved", "run_status",
                        "system_addendum"):
                def raiser(*a, **k):
                    raise ValueError(f"{name} is broken")
                return raiser
            return super().__getattribute__(name)
    run = make_run(hooks=Broken())
    say(run, BREW_LAB)
    assert run.outcome.startswith("Done") and run.error is None
    err = capsys.readouterr().err
    for name in ("message_posted", "turn_started", "call_finished", "record_saved", "run_status", "system_addendum"):
        assert f"hook {name} failed: ValueError: {name} is broken" in err


def test_p8_a_hook_error_class_named_record_rejected_stops_the_run(j2, make_run, mock_mode):
    class RecordRejected(Exception):
        pass
    rec = recorder()

    def reject(name, data):
        if name == "workflows.json":
            raise RecordRejected("workflows.json is not valid")
        return []
    rec.record_saved = reject
    run = make_run(hooks=rec)
    say(run, BREW_LAB)
    assert run.error.startswith("RecordRejected: workflows.json") and run.outcome.startswith("Crashed")
    assert run.status == "waiting" and any(m["text"].startswith("Stopped: RecordRejected") for m in run.chat)
    code, message = rec.of("run_error")[0]
    assert code == "internal" and message == run.error
    assert rec.of("run_status")[-1][0]["status"] == "waiting"


def test_p8_a_hook_error_with_fatal_true_stops_the_run(j2, make_run, mock_mode):
    class Fatal(Exception):
        fatal = True
    rec = recorder()

    def stop(m, questions=None):
        if m["id"] == 3:
            raise Fatal("no")
    rec.message_posted = stop
    run = make_run(hooks=rec)
    say(run, BREW_LAB)
    assert run.error == "Fatal: no" and run.outcome == "Crashed: Fatal: no"


def test_p8_a_model_error_ends_the_run_with_its_code(j2, make_run, mock_mode):
    from sutra_app.engine.llm import ScriptedPort
    from sutra_app.engine.port import QuotaExhausted

    class Quota(ScriptedPort):
        def complete(self, req, on_progress=None):
            if req.tag.call_no == 3:
                raise QuotaExhausted("out of quota")
            return super().complete(req, on_progress)
    mock_mode.configure(Quota(), mock=True, base_tag=base_tag())
    rec = recorder()
    run = make_run(hooks=rec)
    say(run, BREW_LAB)
    assert run.error == "QuotaExhausted: out of quota" and run.outcome == "Crashed: QuotaExhausted: out of quota"
    assert rec.of("run_error") == [("quota", "QuotaExhausted: out of quota")]
    t, o = rec.of("turn_finished")[-1]
    assert o.result == "error" and o.notes[0].startswith("QuotaExhausted")
    assert (Path(run.dir) / "summary.json").is_file() and json.loads((Path(run.dir) / "summary.json").read_text())["status"] == "crashed"


def test_p8_a_run_with_no_hooks_builds_no_records(j2, make_run, mock_mode, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a record was built for NullHooks")
    for name in ("_turn_info", "_call_finished", "_status_snap"):
        monkeypatch.setattr(j2.J2Run, name, refuse)
    run = make_run()
    monkeypatch.setattr(j2.J2Run, "_status_snap", j2.J2Run._status_snap, raising=False)
    say(run, BREW_LAB)
    assert run.outcome.startswith("Done")


# ---- P9: the system addendum -----------------------------------------------------------------------------------------
def system_prompts(run):
    """[function, sha of the system prompt, sha of the prompt] per call. A builder's prompt quotes the receipts of its checks,
    which carry the wall clock ("t": "2026-11-04T13:09:04"); that one field is blanked."""
    stamp = re.compile(r'"t": "\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d"')
    sha = lambda text: hashlib.sha256(stamp.sub('"t": "T"', text).encode()).hexdigest()
    return [(r["fn"], sha(r["system"]), sha(r["prompt"]))
            for r in (json.loads(line) for line in (Path(run.dir) / "calls.jsonl").read_text().splitlines())]


def test_p9_an_empty_addendum_leaves_every_prompt_byte_identical(j2, make_run, mock_mode):
    plain = make_run()
    say(plain, BREW_LAB)
    run, rec = hooked_run(j2, make_run, mock_mode)
    assert rec.addendum == "" and len(rec.of("system_addendum")) == len(run.call_log), "asked before every agent call"
    assert system_prompts(run) == system_prompts(plain) and len(system_prompts(plain)) > 20


def test_p9_an_addendum_is_appended_to_that_functions_system_prompt_only(j2, make_run, mock_mode):
    plain = make_run()
    say(plain, BREW_LAB)
    rec = recorder()
    rec.system_addendum = lambda fn: "\n\n## Node context\nbe brief" if fn == "identity" else ""
    run = make_run(hooks=rec)
    say(run, BREW_LAB)
    for (fn, sys_a, usr_a), (_, sys_b, usr_b) in zip(system_prompts(run), system_prompts(plain)):
        assert usr_a == usr_b
        assert (sys_a != sys_b) == (fn == "identity")
    first = json.loads((Path(run.dir) / "calls.jsonl").read_text().splitlines()[0])
    assert first["system"].endswith("\n\n## Node context\nbe brief")


def test_p9_an_addendum_that_raises_or_is_not_text_is_empty(j2, make_run, mock_mode, capsys):
    plain = make_run()
    say(plain, BREW_LAB)
    rec = recorder()
    rec.system_addendum = lambda fn: (_ for _ in ()).throw(KeyError("no file")) if fn == "identity" else 42
    run = make_run(hooks=rec)
    say(run, BREW_LAB)
    assert system_prompts(run) == system_prompts(plain)
    assert "hook system_addendum failed: KeyError" in capsys.readouterr().err


# ---- P16: Decide for me adds its key to the settings file the host wrote; it never replaces the file ---------------------------------
HOST_SETTINGS = {"realization": True, "record_mode": "log", "nested": {"a": [1, 2]}}      # keys of the host's own resolved-settings dump


def settings_of(run):
    return json.loads((Path(run.dir) / "settings.json").read_text(encoding="utf-8"))


def host_wrote(run, content=HOST_SETTINGS):
    """What the engine host does before J2 starts: the resolved engine settings go to <run>/settings.json."""
    Path(run.dir).mkdir(parents=True, exist_ok=True)
    (Path(run.dir) / "settings.json").write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


def test_p16_decide_for_me_on_at_the_start_adds_its_key_and_keeps_the_hosts_dump(j2, make_run):
    run = make_run()
    host_wrote(run)
    run.set_auto(True)                                   # nothing has been said yet: the switch writes nothing
    assert settings_of(run) == HOST_SETTINGS
    say(run, BREW_LAB)                                   # the run's first turn writes `decide_for_me` next to the host's keys
    assert settings_of(run) == {**HOST_SETTINGS, "decide_for_me": True}


def test_p16_switching_it_on_and_off_later_keeps_the_hosts_dump_too(j2, make_run):
    run = make_run()
    host_wrote(run)
    say(run, BREW_LAB)
    assert settings_of(run) == HOST_SETTINGS, "off: J2 writes nothing at the start"
    run.set_auto(True)
    assert settings_of(run) == {**HOST_SETTINGS, "decide_for_me": True}
    run.set_auto(False)
    assert settings_of(run) == {**HOST_SETTINGS, "decide_for_me": False}


def test_p16_without_a_host_file_the_file_is_j2s_own_one_key(j2, make_run):
    run = make_run()
    run.set_auto(True)
    say(run, BREW_LAB)
    assert settings_of(run) == {"decide_for_me": True}


@pytest.mark.parametrize("torn", ["{not json", "", "   "])
def test_p16_a_settings_file_that_is_not_json_reads_as_empty(j2, make_run, torn):
    run = make_run()
    host_wrote(run, torn)
    run.set_auto(True)
    say(run, BREW_LAB)
    assert settings_of(run) == {"decide_for_me": True}


def test_p16_a_saved_run_reads_decide_for_me_back_from_the_merged_file(j2, make_run):
    on, off = make_run(), make_run()
    for run, flag in ((on, True), (off, False)):
        host_wrote(run)
        run.set_auto(flag)
        say(run, BREW_LAB)
    assert j2.saved_snapshot_dir(str(on.dir), on.run_id)["decide_for_me"] is True
    assert j2.saved_snapshot_dir(str(off.dir), off.run_id)["decide_for_me"] is False
    assert settings_of(on)["nested"] == HOST_SETTINGS["nested"] and "decide_for_me" not in settings_of(off)


def test_p16_the_records_hook_gets_the_merged_file(j2, make_run):
    rec = recorder()
    run = make_run(hooks=rec)
    host_wrote(run)
    run.set_auto(True)
    say(run, BREW_LAB)
    saved = [data for name, data in [c[1:3] for c in rec.calls if c[0] == "record_saved"] if name == "settings.json"]
    assert saved == [{**HOST_SETTINGS, "decide_for_me": True}]


# ---- P7 (timeout): a builder's call that times out is retried once, through the shim ----------------------------------------
def timing_out_port(times):
    """A capturing port that raises a ModelTimeout for the first `times` builder requests."""
    from sutra_app.engine.port import ModelTimeout
    port = captured_port()
    real, left = port.complete, [times]

    def complete(req, on_progress=None):
        if req.tag.function.startswith("W-") and left[0] > 0:
            left[0] -= 1
            port.requests.append(req)
            raise ModelTimeout("took too long")
        return real(req, on_progress)
    port.complete = complete
    return port


def test_p7_only_builder_calls_carry_the_builder_time_limit_to_the_port(j2, make_run, mock_mode):
    run, port = tagged_run(j2, make_run, mock_mode)
    limited = [r for r in port.requests if r.timeout_s is not None]
    assert limited and all(r.tag.function.startswith("W-") and r.timeout_s == 600.0 for r in limited)
    assert all(r.timeout_s is None for r in port.requests if not r.tag.function.startswith("W-"))


def test_p7_a_builder_call_that_times_out_once_is_retried_and_the_run_goes_on(j2, make_run, mock_mode):
    port = timing_out_port(1)
    mock_mode.configure(port, mock=True, base_tag=base_tag())
    run = make_run()
    say(run, BREW_LAB)
    timeouts = [e for e in run.events if e["type"] == "builder_timeout"]
    assert len(timeouts) == 1 and "retried once" in timeouts[0]["detail"]
    assert run.error is None and run.done


def test_p7_a_builder_call_that_times_out_twice_is_not_retried_again(j2, make_run, mock_mode):
    port = timing_out_port(2)
    mock_mode.configure(port, mock=True, base_tag=base_tag())
    run = make_run()
    say(run, BREW_LAB)
    timeouts = [e for e in run.events if e["type"] == "builder_timeout"]
    assert len(timeouts) == 2 and "not retried again" in timeouts[1]["detail"]
    assert "retried once" in timeouts[0]["detail"] and run.error is None, "J2 handles the second stop itself (j2.py): the envelope retries"


# ---- P14: a `single` output keeps its output and makes no planner call; no output yet is not an error ---------------------------
def test_p14_a_run_with_no_output_yet_plans_its_stages_without_crashing(j2, make_run, mock_mode):
    port = captured_port()
    mock_mode.configure(port, mock=True, base_tag=base_tag())
    run = make_run()
    assert run.out is None
    say(run, BREW_LAB)
    assert run.error is None and run.out is not None, "the planner chose the type"


def test_p14_a_single_output_returns_before_the_planner_call(j2, make_run, mock_mode):
    port = captured_port()
    mock_mode.configure(port, mock=True, base_tag=base_tag())
    run = make_run()
    run.out, run.request = {"single": True}, "update the PRD in the repo"
    run._plan_stages()
    assert port.requests == [] and not run.stages and not run.goal


# ---- P17 and P18: j2_types (sync 5) ---------------------------------------------------------------------------------------------
@pytest.fixture
def jt(tmp_path):
    """A fresh j2_types whose local store is under tmp_path/store (J2_TYPES_DIR is read when the module is imported)."""
    with fresh_j2(tmp_path / "env", J2_TYPES_DIR=tmp_path / "store") as mod:
        yield mod.j2_types


SECTIONS = ["Beans", "Water"]


def package_dir(jt):
    return Path(jt.__file__).parent


def test_p17_with_the_store_set_create_writes_under_it_and_nothing_under_the_package(jt, tmp_path):
    store, package = tmp_path / "store", package_dir(jt)
    before = sorted(p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file())
    assert jt.LOCAL_TYPES_PATH == str(store / "types.local.json") and jt.LOCAL_LIBRARY_DIR == str(store / "templates")
    entry = jt.create("brew_notes", "Brew notes", SECTIONS, form="document")
    assert entry["name"] == "brew_notes" and "brew_notes" in jt.names()
    assert (store / "types.local.json").is_file() and (store / "templates" / "brew_notes" / "generic.json").is_file()
    assert Path(jt.template_path("brew_notes")) == store / "templates" / "brew_notes" / "generic.json"
    assert sorted(p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file()) == before
    assert not (package / "artifacts" / "types.local.json").exists() and not (package / "library" / "types").exists()
    assert not list(store.glob("*.tmp")), "the temp file of the atomic write is gone"


def test_p17_without_the_store_j2s_own_places_apply(tmp_path):
    with fresh_j2(tmp_path / "env") as mod:
        t = mod.j2_types
        assert t.LOCAL_TYPES_PATH == str(Path(t.__file__).parent / "artifacts" / "types.local.json")
        assert t.LOCAL_LIBRARY_DIR == str(Path(t.__file__).parent / "library" / "types")


def test_p17_a_held_lock_gives_a_value_error_and_writes_nothing(jt, tmp_path, monkeypatch):
    from sutra_app import oslayer
    monkeypatch.setattr(jt, "TYPES_LOCK_WAIT_S", 0.2)
    store = tmp_path / "store"
    store.mkdir()
    fd = os.open(store / ".lock", os.O_RDWR | oslayer.O_BINARY | os.O_CREAT, 0o600)
    try:
        assert oslayer.try_lock(fd)
        with pytest.raises(ValueError, match="locked by another run"):
            jt.create("brew_notes", "Brew notes", SECTIONS, form="document")
    finally:
        oslayer.unlock(fd)
        os.close(fd)
    assert not (store / "types.local.json").exists()
    assert jt.create("brew_notes", "Brew notes", SECTIONS, form="document")["name"] == "brew_notes", "free again"


def test_p17_two_threads_creating_different_types_lose_neither(jt, tmp_path):
    errors, names = [], ["alpha_notes", "beta_notes", "gamma_notes", "delta_notes"]

    def make(name):
        try:
            jt.create(name, name.replace("_", " ").title(), SECTIONS, form="document")
        except Exception as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=make, args=(n,)) for n in names]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert errors == []
    saved = json.loads((tmp_path / "store" / "types.local.json").read_text(encoding="utf-8"))["types"]
    assert sorted(t["name"] for t in saved) == sorted(names)
    assert all((tmp_path / "store" / "templates" / n / "generic.json").is_file() for n in names)


def host_entry(tmp_path, jt, name="host_doc", owner="tests", **extra):
    template = tmp_path / f"{name}.generic.json"
    template.write_text(json.dumps(jt.template_for(name, "Host doc", SECTIONS), indent=1) + "\n", encoding="utf-8")
    return {"name": name, "kind": "type", "label": "Host doc", "tag": "Host", "color": "--other", "form": "document",
            "template": str(template), "file": f"{name}.md", "deliverable": False, "triggers": [], "groups": [],
            "depends_on": [], "host": owner, **extra}


def test_p18_a_registered_type_is_known_chosen_by_default_and_carries_its_extras(jt, tmp_path, monkeypatch):
    calls = lambda: "mock"
    jt.register(host_entry(tmp_path, jt), {"single": True, "workspace": "edit", "mock_charter": calls})
    assert "host_doc" in jt.names()
    monkeypatch.setenv("J2_OUTPUT", "host_doc")
    assert jt.default() == "host_doc"
    out = jt.load("host_doc")
    assert out["single"] is True and out["workspace"] == "edit" and out["mock_charter"] is calls
    assert out["sections"] == tuple(SECTIONS) and out["file"] == "host_doc.md"
    assert jt.load("website").get("single") is None, "the extras belong to the type that registered them"


def test_p18_a_host_type_is_not_a_planner_choice_and_not_a_template_library_artifact(jt, tmp_path):
    jt.register(host_entry(tmp_path, jt))
    realization = importlib.import_module(f"{ENGINE}.j2_realization")
    assert "host_doc" not in jt.templated()
    assert "host_doc" not in str(realization.type_list())
    assert "website" in jt.templated()


def test_p18_every_entry_stays_json_serialisable_with_a_callable_in_the_extras(jt, tmp_path):
    jt.register(host_entry(tmp_path, jt), {"single": True, "mock_atom": lambda *a: {}})
    json.dumps(jt.entries())
    json.dumps(jt.HOST["host_doc"]["entry"])
    arts = importlib.import_module(f"{ENGINE}.j2_artifacts")
    json.dumps(arts.load_types())


def test_p18_a_name_the_data_has_is_refused_the_same_owner_replaces_another_owner_is_refused(jt, tmp_path):
    with pytest.raises(ValueError, match="already a type"):
        jt.register(host_entry(tmp_path, jt, name="website"))
    jt.register(host_entry(tmp_path, jt, label="First"))
    jt.register(host_entry(tmp_path, jt, label="Second"))
    assert [e["label"] for e in jt.entries() if e["name"] == "host_doc"] == ["Second"] and list(jt.HOST) == ["host_doc"]
    with pytest.raises(ValueError, match="already registered by tests"):
        jt.register(host_entry(tmp_path, jt, owner="someone_else"))


def test_p18_an_entry_must_be_a_type_with_a_good_name_and_an_owner(jt, tmp_path):
    good = host_entry(tmp_path, jt)
    for bad, why in (({**good, "kind": "record"}, "kind: type"), ({**good, "name": "Bad Name"}, "must match"),
                     ({**{k: v for k, v in good.items() if k != "host"}}, "owner"), ({**good, "x": object()}, "JSON-safe")):
        with pytest.raises(ValueError, match=why):
            jt.register(bad)
    assert jt.HOST == {}


def test_p18_a_local_type_with_a_host_name_is_refused_by_create(jt, tmp_path):
    jt.register(host_entry(tmp_path, jt))
    with pytest.raises(ValueError):
        jt.create("host_doc", "Host doc", SECTIONS, form="document")


def test_p18_register_clears_the_cache_so_the_type_shows_at_once(jt, tmp_path):
    before = jt.names()
    jt.register(host_entry(tmp_path, jt))
    assert set(jt.names()) == set(before) | {"host_doc"}


# ---- sync 6: P7 on a run template's planner call, P8 order at the run end, P9 and the delay, P19 the reviewer switch ------------------
SEED_LIBRARY = Path(__file__).resolve().parents[2] / "sutra_app" / "engine" / "seed" / "library"
RUN_TEMPLATE = "thread-boutique-website"          # a mock-made run template of the seed (the runs here are mock runs)


@pytest.fixture
def j2_tpl(tmp_path):
    """J2 imported with run templates on (J2_RUN_TEMPLATES) and the seed library as its library."""
    import shutil
    shutil.copytree(SEED_LIBRARY, tmp_path / "env" / "library")
    with fresh_j2(tmp_path / "env", J2_RUN_TEMPLATES="1") as mod:
        yield mod


def test_p7_the_planner_call_of_a_run_template_run_is_tagged_adaptation_step_2(j2_tpl, tmp_path, mock_mode):
    """`_run_tpl_start(said) if self.run_tpl else self._deliverables(said)` is one expression inside the P7 block: the planner
    call the whole-template path makes (it calls `_deliverables` itself) is charged to Adaptation, like the plain one."""
    port = captured_port()
    mock_mode.configure(port, mock=True, base_tag=base_tag())
    run = j2_tpl.J2Run(run_dir=tmp_path / "runs" / "j2-20261104-100001-7f3a")
    assert run.set_run_template(RUN_TEMPLATE, "all") is True and run.run_tpl
    assert run.user_says(BREW_LAB) is True
    deadline = time.time() + 60
    while run.status != "waiting":
        assert time.time() < deadline
        time.sleep(0.003)
    first = port.requests[0].tag
    assert (first.function, first.step) == ("adaptation", 2), "the first model call of a template run is the planner's, tagged"
    settle(run)


def test_p7_the_planner_expression_is_one_statement_inside_the_tagged_block():
    text = (Path(__file__).resolve().parents[2] / "sutra_app" / "engine" / "j2.py").read_text(encoding="utf-8")
    block = ('        with llm.tagged(function="adaptation", step=2, cycle=self.cycle, stage=self.stage_kind or self.output):'
             '      # P7: Adaptation\'s planner call, made before its turn\n'
             '            chosen = self._run_tpl_start(said) if self.run_tpl else self._deliverables(said)')
    assert text.count(block) == 1


def test_p8_the_run_end_hook_fires_after_the_report_is_made_and_the_reviewer_is_running(j2, make_run, mock_mode):
    """P8's anchor moved in sync 6: `_make_report` starts the reviewer thread, then the status is `waiting`, then the hook. The
    placeholder report is on disk when `run_status("waiting")` is heard; the host's join (D179) is what makes the folder stable."""
    seen = {}
    rec = recorder()
    original = rec.run_status

    def run_status(snap):
        original(snap)
        if snap["status"] == "waiting":
            seen["report"] = json.loads((Path(rec.run.dir) / "report.json").read_text())
            seen["thread"] = getattr(rec.run, "review_thread", None)
    rec.run_status = run_status
    mock_mode.configure(mock=True, base_tag=base_tag())
    run = make_run(hooks=rec)
    rec.run = run
    say(run, BREW_LAB)
    assert seen["report"]["review"]["verdict"] and seen["thread"] is not None, "report.json existed and the reviewer thread was started"
    settle(run)
    assert rec.of("run_status")[-1][0]["status"] == "waiting"


def test_p9_the_delay_lines_of_call_use_call_delay_and_the_other_two_sites_are_untouched():
    text = (Path(__file__).resolve().parents[2] / "sutra_app" / "engine" / "j2.py").read_text(encoding="utf-8")
    assert text.count("if self.calls and call_delay():") == 3 and text.count("time.sleep(call_delay())") == 3
    at = text.index("system = system_prompt(fn, reply_format, self._builder_for(fn))")
    assert text[at:at + 400].count("system_addendum") == 1 and text[at:at + 600].count("call_delay()") == 2


def test_p9_an_addendum_still_reaches_the_prompt_with_the_new_delay(j2, make_run, mock_mode):
    rec = recorder()
    rec.system_addendum = lambda fn: "\n\n## Node context\nbe brief" if fn == "identity" else ""
    run = make_run(hooks=rec)
    say(run, BREW_LAB)
    settle(run)
    first = json.loads((Path(run.dir) / "calls.jsonl").read_text().splitlines()[0])
    assert first["system"].endswith("\n\n## Node context\nbe brief")


def test_p9_a_mock_run_has_no_call_delay(j2):
    assert j2.call_delay() == 0


# ---- P19: the reviewer switch (D179) ---------------------------------------------------------------------------------------------
def reviewer_calls(port):
    return [r for r in port.requests if r.tag.function == "reviewer"]


def run_with_hooks(j2, make_run, mock_mode, hooks):
    port = captured_port()
    mock_mode.configure(port, mock=True, base_tag=base_tag())
    run = make_run(**({"hooks": hooks} if hooks is not None else {}))
    if hooks is not None and hasattr(hooks, "run"):
        hooks.run = run
    say(run, BREW_LAB)
    settle(run)
    return run, port


def verdict_of(run):
    return json.loads((Path(run.dir) / "report.json").read_text())["review"]["verdict"]


def test_p19_the_reviewer_runs_under_null_hooks_as_before(j2, make_run, mock_mode):
    run, port = run_with_hooks(j2, make_run, mock_mode, None)
    assert len(reviewer_calls(port)) == 1 and "switched off" not in verdict_of(run)
    assert json.loads((Path(run.dir) / "report.json").read_text())["metrics"]["ai_calls"] == run.calls, "the reviewer's call is counted"


def test_p19_a_hook_that_says_true_or_nothing_leaves_the_reviewer_on(j2, make_run, mock_mode):
    for answer in (True, None, "no", 0):
        rec = recorder()
        rec.review_enabled = lambda answer=answer: answer
        run, port = run_with_hooks(j2, make_run, mock_mode, rec)
        assert len(reviewer_calls(port)) == 1, answer      # only an explicit False switches it off
        assert "switched off" not in verdict_of(run), answer


def test_p19_an_explicit_false_switches_the_reviewer_off_and_the_report_says_so(j2, make_run, mock_mode):
    rec = recorder()
    rec.review_enabled = lambda: False
    run, port = run_with_hooks(j2, make_run, mock_mode, rec)
    assert reviewer_calls(port) == [] and getattr(run, "review_thread", None) is None
    assert verdict_of(run) == "The reviewer is switched off in this team's settings."
    report = json.loads((Path(run.dir) / "report.json").read_text())
    assert report["metrics"]["ai_calls"] == run.calls, "the reviewer's call is not counted"
    assert "switched off in this team's settings" in (Path(run.dir) / "report.md").read_text()
    assert run.outcome.startswith("Done")


def test_p19_a_pause_for_the_requester_keeps_its_own_placeholder_even_when_the_reviewer_is_off(j2, make_run, mock_mode):
    rec = recorder()
    rec.review_enabled = lambda: False
    mock_mode.configure(mock=True, base_tag=base_tag())
    run = make_run(hooks=rec)
    say(run, VAGUE[0])
    assert run.paused and verdict_of(run).startswith("Paused for the Requester")


def test_p19_a_hook_that_raises_does_not_switch_the_reviewer_off(j2, make_run, mock_mode, capsys):
    rec = recorder()

    def boom():
        raise RuntimeError("hook failed")
    rec.review_enabled = boom
    run, port = run_with_hooks(j2, make_run, mock_mode, rec)
    assert len(reviewer_calls(port)) == 1 and run.error is None


def test_p19_the_edit_is_in_the_vendored_make_report():
    text = (Path(__file__).resolve().parents[2] / "sutra_app" / "engine" / "j2.py").read_text(encoding="utf-8")
    assert text.count('off = review and self._hook("review_enabled") is False') == 1
    assert text.count("The reviewer is switched off in this team's settings.") == 1


# ---- P21 (D245): the host's own run files during a builder tools call ----------------------------------------------------------

def tools_call(j2, run, said=None, extra=None, temps=(), inside=None):
    """One builder call with tools, through J2Run.call in mock mode: the scripted reply plays the CLI (it writes in the builder's
    folder, and `said` is what its tool calls named) and the app's host (it updates agent_live.json and snapshot.json meanwhile)."""
    from sutra_app.engine import llm
    run._apply_output("website")
    cwd = Path(run.dir) / "out"
    cwd.mkdir(parents=True, exist_ok=True)
    for name in ("agent_live.json", "snapshot.json"):
        (Path(run.dir) / name).write_text("{}")
    tools = {"tools": ["Write"], "allow": ["Write"], "cwd": str(cwd), "root": str(run.dir), "usd": 1.0, "log_chars": 200,
             "max_files": 50, "max_bytes": 1_000_000}

    def mock():
        (cwd / "build.py").write_text("print('built')\n")
        for name, body in (inside or {}).items():      # more files in the builder's folder (P34: the CLI's .claude)
            (cwd / name).parent.mkdir(parents=True, exist_ok=True)
            (cwd / name).write_text(body)
        (Path(run.dir) / "agent_live.json").write_text(json.dumps({"agents": {"W-1": {"text": "writing"}}}))     # the host's live view
        (Path(run.dir) / "snapshot.json").write_text(json.dumps({"turn": "W-1"}))                                  # the host's snapshot
        for name, body in (extra or {}).items():
            (Path(run.dir) / name).write_text(body)
        for name in temps:              # an atomic write caught mid-way: its temp file is there when the call ends
            from sutra_app import oslayer
            oslayer.temp_path(Path(run.dir) / name).write_text("{")
        llm.LAST_META["tool_calls"] = [{"n": 1, "name": "Write", "input": said or {"file_path": "build.py"}, "ok": True}]
        return json.dumps({"say": "built"})
    return run.call("identity", '{"say": str}', "build it", mock, tools=tools)


def test_p21_host_files_written_during_a_tools_call_are_not_the_builders_writes(j2, make_run):
    run = make_run()
    run.post("user", "go")
    tools_call(j2, run)
    assert not [e for e in run.events if e["type"] == "outside_write"], "the host's agent_live.json and snapshot.json are not the builder's"
    from sutra_app.engine.rehydrate import HOST_FILES
    assert {"agent_live.json", "snapshot.json", "events.jsonl"} <= set(HOST_FILES)


def test_p21_a_host_file_the_cli_names_and_any_other_file_outside_are_still_stopped(j2, make_run):
    run = make_run()
    run.post("user", "go")
    with pytest.raises(j2.BuilderToolFault, match="snapshot.json"):
        tools_call(j2, run, said={"command": "echo x > ../snapshot.json"})                 # the CLI wrote a host file itself
    run = make_run()
    run.post("user", "go")
    with pytest.raises(j2.BuilderToolFault, match="notes.txt"):
        tools_call(j2, run, extra={"notes.txt": "x"})                                         # not a host file: outside its folder


def test_p21_a_host_file_caught_mid_write_is_the_hosts_and_a_builders_temp_file_still_counts(j2, make_run):
    from sutra_app import oslayer
    t = oslayer.temp_path("runs/r/agent_live.json")
    assert Path(oslayer.temp_target(t)) == Path("runs/r/agent_live.json") and oslayer.temp_target(t.name) == "agent_live.json"      # the OS's separator
    assert oslayer.temp_target("agent_live.json") is None and oslayer.temp_target(".agent_live.json.tmp") is None
    run = make_run()
    run.post("user", "go")
    tools_call(j2, run, temps=("agent_live.json", "snapshot.json"))
    assert not [e for e in run.events if e["type"] == "outside_write"], "the host's temp files, mid-write, are the host's"
    run = make_run()
    run.post("user", "go")
    with pytest.raises(j2.BuilderToolFault, match=r"\.notes\.txt\.[0-9a-f]{8}\.tmp"):
        tools_call(j2, run, temps=("notes.txt",))                                            # not a host file's temp: outside its folder


# ---- P22 (D246): a real run's item covered by another workflow ------------------------------------------------------------------
# The proposals of beta run j2-20261118-110800-0c75 (software-engineering): Adaptation's plan (calls 15 to 17) and its fix (call 30),
# with the Requester's folder replaced by a temp folder. "Write run_on_sort_me.md" covered item 3, which the real run of
# "Build sort_files.py" checks, and the validator refused the script four times saying item 3 must leave its covers.
FT = "copy_script"
SORT_DONE_WHEN = ["sort_files.py sorts the files in a given folder into subfolders named for each file's extension.",
                  "test_sort_files.py is an automated test that checks sort_files.py puts each file in its folder, and passes.",
                  "Run on the sort-me folder, the script leaves a.pdf in pdf/, b.jpg in jpg/, c.txt in txt/ and d.csv in csv/."]


@pytest.fixture(scope="module")
def j2ft(tmp_path_factory):
    """J2 with the folder type FT made in its own type store (as J2's flow test makes it)."""
    base = tmp_path_factory.mktemp("j2-ft")
    with fresh_j2(base, J2_TYPES_DIR=base / "types") as mod:
        mod.j2_types.create(FT, "Script", None, form="agent")
        mod._data_type.cache_clear()
        yield mod


@pytest.fixture
def sort_run(j2ft, tmp_path):
    real = tmp_path / "sort-me"
    real.mkdir()
    counter = itertools.count(1)

    def make():
        run = j2ft.J2Run(run_dir=tmp_path / "runs" / f"j2-20261118-1108{next(counter):02d}-0c75")
        run._apply_output(FT)
        run.request = f"Build sort_files.py with a test, then run it on {real}"
        run.goal, run.budget = {"statement": "x", "done_when": list(SORT_DONE_WHEN)}, 100
        os.makedirs(run._out_dir(), exist_ok=True)
        return run
    return make, str(real)


def sort_proposals(real, *, fix=False):
    """Calls 15 to 17 of the run (fix=False): the script with its real run, the test, the run notes; call 43 (fix=True): the
    script again, alone, after the run notes were registered as W-3."""
    def wf(name, out, covers, deps, real_run=None):
        atom = {"id": "a1", "goal": f"write {out}", "context": ["charter"], "constraints": ["only the folder"],
                "how": {"kind": "AI", "agent": "Builder", "steps": f"write {out}"},
                "expected_output": [{"text": f"{out} exists", "kind": "file", "target": out}],
                "verification": [{"text": f"{out} exists", "type": "file-exists", "target": out, "expect": True}]}
        return {"name": name, "kind": "build", "goal_gap": "x", "outputs": [out], "completion_check": "z", "covers": covers,
                "dependencies": deps, "parts": ["agent_file"] * max(1, len(covers)), "atoms": [atom], "real_run": real_run}
    rr = {"command": ["python3", "sort_files.py", real], "folder": real, "reads": [],
          "why": "The brief asks to run the script on the Requester's own folder.", "checks": [3],
          "expect": {"created": ["done.txt"], "changed": [], "deleted": []}}      # P35 (D438): what P31_OK and P33_OK create
    script = wf("Build sort_files.py", "sort_files.py", [1], [], rr)
    if fix:
        return [script]
    return [script, wf("Write test_sort_files.py", "test_sort_files.py", [2], ["Build sort_files.py"]),
            wf("Write run_on_sort_me.md", "run_on_sort_me.md", [3], ["Build sort_files.py", "Write test_sort_files.py"])]


def notes_alone(real):
    """The run notes registered on their own (W-3 of the run, covers [3]), before the script came back."""
    return [{**sort_proposals(real)[2], "dependencies": []}]


def test_p22_a_workflow_without_a_real_run_that_covers_its_item_is_refused_and_the_real_run_workflow_registers(sort_run):
    make, real = sort_run
    run = make()
    reg, refused, _ = run._register(sort_proposals(real))
    assert [w["name"] for w in reg] == ["Build sort_files.py", "Write test_sort_files.py"], refused
    assert reg[0]["real_run"]["checks"] == [3] and reg[0]["covers"] == [1]
    assert refused == ["Write run_on_sort_me.md (it covers done-when item(s) 3, which the real run of 'Build sort_files.py' "
                       "checks: a real run's receipt decides such an item, so a workflow without a real run doesn't cover it; "
                       "take it out of covers)"]


@pytest.mark.parametrize("status", ["registered", "held"])
def test_p22_a_waiting_workflow_that_covers_the_item_is_named_with_supersede_or_replace(sort_run, status):
    """The run notes are W-1, registered (or held), not built, when the script comes back: the refusal names W-1 and says
    to supersede or replace it."""
    make, real = sort_run
    run = make()
    run._register(notes_alone(real))
    run.workflows[0]["status"] = status
    reg, refused, _ = run._register(sort_proposals(real, fix=True))
    who = "W-1 Write run_on_sort_me.md"
    assert not reg and refused == [f"Build sort_files.py (done-when item 3 is checked by this real run, but {who} covers it, so "
                                   f"the conflict is in {who}: it is {status} and not built, so supersede it (name W-1 in "
                                   "\"replaces\") or replace it with a workflow that doesn't cover item 3; this workflow keeps "
                                   "it in real_run checks)"]


def test_p22_following_the_advice_supersedes_the_waiting_workflow_and_the_real_run_workflow_registers(sort_run):
    make, real = sort_run
    run = make()
    run._register(notes_alone(real))
    notes = {**notes_alone(real)[0], "name": "Rewrite run_on_sort_me.md", "covers": [], "replaces": ["W-1"]}
    reg, refused, _ = run._register(sort_proposals(real, fix=True) + [notes])
    assert run.workflows[0]["status"] == "superseded" and not refused, refused
    assert [w["name"] for w in reg] == ["Build sort_files.py", "Rewrite run_on_sort_me.md"]


def test_p22_a_done_workflow_that_covers_the_item_cant_be_replaced_and_the_repeat_goes_to_the_requester(sort_run):
    """Cycles 2 to 4 of the run: W-3 (here W-1) was built, so it can't be superseded (_supersede takes only registered or held):
    the refusal says the item can't be met by this real run in this run, and the second identical refusal stops the cycle."""
    make, real = sort_run
    run = make()
    run._register(notes_alone(real))
    run.workflows[0]["status"] = "done"
    reg, refused, _ = run._register(sort_proposals(real, fix=True))
    who = "W-1 Write run_on_sort_me.md"
    assert not reg and refused == [f"Build sort_files.py (done-when item 3 is checked by this real run, but {who} covers it, so "
                                   f"the conflict is in {who}: it is done and can't be superseded or replaced, so item 3 "
                                   "can't be met by this real run in this run)"]
    run._agree(sort_proposals(real, fix=True))
    assert run.turn == "identity" and run.handoff["kind"] == "limit" and "can't be superseded" in run.handoff["reason"]


def test_p22_the_real_run_workflow_covering_its_own_item_keeps_the_old_message(sort_run):
    make, real = sort_run
    script = sort_proposals(real, fix=True)[0]
    reg, refused, _ = make()._register([{**script, "covers": [1, 3], "parts": ["agent_file"] * 2}])
    assert not reg and "so no workflow covers it: take it out of covers and keep it in real_run checks" in refused[0]


def test_p22_the_same_rejection_of_the_same_workflow_twice_in_a_row_stops_the_cycle(sort_run):
    """Cycles 2 to 4 of the run refused the script again and again; the second identical refusal stops the cycle: Identity
    asks the Requester (a limit), and "keep going" resumes where the validator was going."""
    make, real = sort_run
    run = make()
    run._register(notes_alone(real))
    run.workflows[0]["status"] = "done"                       # W-3 was built before the script came back                  # W-3, the run notes
    run._agree(sort_proposals(real, fix=True))                # first refusal: back to Adaptation
    assert run.turn == "adaptation" and not run.repeat_rejected
    run._agree(sort_proposals(real, fix=True))                # the same refusal again
    assert run.turn == "identity" and run.handoff["kind"] == "limit", run.handoff
    assert run.handoff["reason"].startswith("The same failure came back twice in a row: the validator rejected Build sort_files.py")
    assert "resume" not in run.handoff                        # nothing was registered: "keep going" starts a new cycle
    assert [e for e in run.events if e["type"] == "repeat" and "Build sort_files.py" in json.dumps(e)]


def test_p22_a_repeated_rejection_beside_new_work_stops_the_cycle_and_keep_going_builds_it(sort_run):
    make, real = sort_run
    run = make()
    run._register(notes_alone(real))
    run.workflows[0]["status"] = "done"                       # W-3 was built before the script came back
    run._agree(sort_proposals(real, fix=True))
    test = sort_proposals(real)[1]
    run._agree(sort_proposals(real, fix=True) + [{**test, "dependencies": []}])
    assert [w["name"] for w in run.workflows if w["status"] == "registered"][-1] == "Write test_sort_files.py"
    assert run.handoff["kind"] == "limit" and run.handoff["resume"] == {"to": "coordination", "handoff": {"kind": "schedule"}}


def test_p22_a_different_rejection_in_between_is_not_twice_in_a_row(sort_run):
    make, real = sort_run
    run = make()
    run._register(notes_alone(real))
    run.workflows[0]["status"] = "done"                       # W-3 was built before the script came back
    run._agree(sort_proposals(real, fix=True))
    run._agree([{"name": "Something else"}])                 # another refusal in between
    run._agree(sort_proposals(real, fix=True))
    assert run.turn == "adaptation", run.handoff


def test_p22_a_renamed_proposal_rejected_for_the_same_reason_stops_the_cycle(sort_run):
    """D431 amends P22: the repeat is the rejection's reason, whatever the workflow is called (run 17e1's replacements were
    reworded copies)."""
    make, real = sort_run
    run = make()
    run._register(notes_alone(real))
    run.workflows[0]["status"] = "done"
    run._agree(sort_proposals(real, fix=True))
    assert run.turn == "adaptation"
    run._agree([{**sort_proposals(real, fix=True)[0], "name": "Build the sorter"}])       # renamed, refused for the same reason
    assert run.turn == "identity" and run.handoff["kind"] == "limit", run.handoff
    assert run.handoff["reason"].startswith("The same failure came back twice in a row: the validator rejected Build the sorter")


def test_p22_renaming_the_other_workflow_a_rejection_names_is_still_the_same_rejection(sort_run):
    """Review R1-2: the repeat compares the rejection's code-set key (its rule and the item numbers), never a name. The run
    notes are refused for covering item 3, which the real run checks; the refusal names the real-run workflow, and renaming
    that workflow between two calls changes the words, not the rejection."""
    make, real = sort_run
    run = make()
    script, test, notes = sort_proposals(real)
    run._register([script, notes])
    assert [x["workflow"] for x in run.rejections] == ["Write run_on_sort_me.md"] and not run.repeat_rejected
    run._register([{**script, "name": "Build the sorter"}, notes])
    assert "'Build the sorter'" in run.rejections[-1]["reason"]
    assert [x[0] for x in run.repeat_rejected] == ["Write run_on_sort_me.md"], run.rejections


def test_p22_a_rejection_of_another_kind_is_not_the_same_rejection(sort_run):
    make, real = sort_run
    run = make()
    script, test, notes = sort_proposals(real)
    run._register([script, notes])                                      # refused: it covers the real run's item
    run._register([{**notes, "completion_check": ""}])                   # refused: a required field is missing
    assert run.rejections[-1]["workflow"] == "Write run_on_sort_me.md" and not run.repeat_rejected


# ---- P23 (D247): ended_workable only for a clean "Done:" end ---------------------------------------------------------------------

def ended(run_dir, outcome, fail=False, **audit_keys):
    """A run folder as J2 leaves it: audits.json (a document audit, item 2 failing when `fail`) and summary.json with `outcome`."""
    run_dir.mkdir(parents=True, exist_ok=True)
    results = [{"id": "F-1", "item": 1, "criterion": "the policy is written", "pass": True, "verdict": "PASS", "note": "ok"},
               {"id": "F-2", "item": 2, "criterion": "the script has been run on the folder", "pass": not fail,
                "verdict": "FAIL" if fail else "PASS", "note": ""}]
    (run_dir / "audits.json").write_text(json.dumps([{"output": "prd", "results": results, "rubric": [], "conditions": [], **audit_keys}]))
    if outcome is not None:
        (run_dir / "summary.json").write_text(json.dumps({"outcome": outcome}))
    return run_dir


PENDING = dict(fail=True, after_real_run=["the script has been run on the folder"])       # a real run that never ran
ACCEPTED = dict(fail=True, accepted=["the script has been run on the folder"])             # finished as it is


def test_p23_ended_workable_is_true_only_for_a_clean_done(j2, tmp_path):
    assert j2.ended_workable(ended(tmp_path / "clean", "Done: the PRD is workable."))
    for name, outcome, keys in (("pending", "Done with open items: the real run has not run.", PENDING),
                                ("accepted", "Done with open items: finished as it is.", ACCEPTED),
                                ("done-accepted", "Done: the PRD is workable.", ACCEPTED),           # an accepted item never counts as passing
                                ("done-pending", "Done: the PRD is workable.", PENDING)):
        d = ended(tmp_path / name, outcome, **keys)
        audit = json.loads((d / "audits.json").read_text())[-1]
        assert j2.workable(audit) == [], (name, "J2's workable() takes these items as passing: the hole P23 closes")
        assert not j2.ended_workable(d), name
    assert not j2.ended_workable(ended(tmp_path / "no-summary", None)), "no summary.json: not a clean end"
    assert not j2.ended_workable(ended(tmp_path / "stopped", "Stopped: the plan chose nothing J2 can build."))
    assert "P23 (D247)" in j2.ended_workable.__doc__


def test_p23_a_run_that_ended_with_open_items_is_never_saved_as_a_run_template(j2, make_run, monkeypatch):
    saved = []
    monkeypatch.setenv("J2_RUN_TEMPLATES", "1")
    monkeypatch.setattr(j2.j2_template_lib, "auto_save_run_template", lambda d: saved.append(d) or (None, False, "test"))
    for outcome, keys in (("Done with open items: the real run has not run.", PENDING),
                          ("Done with open items: finished as it is.", ACCEPTED)):
        run = make_run()
        ended(Path(run.dir), outcome, **keys)
        run.outcome = outcome
        run._save_run_template()
        assert not saved, outcome
    run = make_run()
    ended(Path(run.dir), "Done: the PRD is workable.")
    run.outcome = "Done: the PRD is workable."
    run._save_run_template()
    assert saved == [run.dir], "a clean Done: is saved"


def test_p23_a_run_that_ended_with_open_items_is_never_reused_as_a_folder(j2, make_run, monkeypatch, tmp_path):
    for name, outcome, keys, reused in (("pending", "Done with open items: the real run has not run.", PENDING, False),
                                        ("accepted", "Done with open items: finished as it is.", ACCEPTED, False),
                                        ("clean", "Done: the script is workable.", {}, True)):
        src = ended(tmp_path / "runs" / f"j2-src-{name}", outcome, **keys)
        (src / "copy").mkdir()
        (src / "copy" / "copy_files.py").write_text("print('copy')\n")
        run = make_run()
        run.output = "copy_script"
        run.run_tpl = {"id": "t", "from_run": src.name, "outputs": {"copy_script": {"folder": "copy", "files": ["copy_files.py"]}}}
        monkeypatch.setattr(j2, "saved_dir", lambda n, _src=src: str(_src) if n == _src.name else None)
        monkeypatch.setattr(j2.j2_template_lib, "get_run_template", lambda tid: None)
        monkeypatch.setattr(j2.j2_template_lib, "folder_decision", lambda *a, **k: {"action": "reused"})
        cwd = tmp_path / f"out-{name}"
        cwd.mkdir()
        try:
            got = run._reuse_folder({"id": "W-1", "atoms": [{"id": "W-1.a1"}]}, str(cwd))
        except Exception:          # past the check, the rest of the reuse needs a real run template: the copy is what this test reads
            got = "past the check"
        assert bool(os.listdir(cwd)) is reused, (name, os.listdir(cwd))
        if not reused:
            assert got is None and any(e["type"] == "reuse_skipped" for e in run.events), name


# ---- P24 (D250): Priority's move is a workflow's id and its envelope -------------------------------------------------------------
# Beta run j2-20261118-090053-4a9c (people-hr): Priority COUNTERed Adaptation's three fixes from 24 to 18 (6, 7, 5) and also added
# F-10 to their "fixes"; the validator logged "kept as Adaptation proposed it" as an autofix. Fixture: Adaptation's proposal (chat 32)
# and Priority's COUNTER (call 14), with the three registered workflows they revise.
P24 = json.loads((Path(__file__).parent / "fixtures" / "p24" / "counter_4a9c.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def j2hp(tmp_path_factory):
    """J2 with the run's document type (hiring_policy, its nine sections) made in its own type store."""
    base = tmp_path_factory.mktemp("j2-hp")
    with fresh_j2(base, J2_TYPES_DIR=base / "types") as mod:
        mod.j2_types.create("hiring_policy", "Hiring policy", P24["sections"], practice=True, form="document")
        mod._data_type.cache_clear()
        yield mod


@pytest.fixture
def hp_run(j2hp, tmp_path, monkeypatch):
    """The run as Priority found it: W-1 to W-3 done (72 of 100 spent), Adaptation's three fixes proposed. `rates`: the rate card
    (none by default, as in the run)."""
    def make(rates=None):
        run = j2hp.J2Run(run_dir=tmp_path / "runs" / "j2-20261118-090053-4a9c")
        run._apply_output("hiring_policy")
        monkeypatch.setattr(j2hp, "RATES", rates or {})
        run.goal, run.budget, run.spent = {"statement": "x", "done_when": list(P24["done_when"])}, P24["budget"], P24["spent_before"]
        run.workflows = [{**w, "covers": [], "fixes": [], "section": w["id"], "envelope": {"money_limit": w["cost"]}, "charged": True,
                          "outputs": [], "dependencies": [], "kind": "build", "cycle": 1} for w in P24["registered_before"]]
        run.cycle = 2
        table = j2hp.norm(json.loads(json.dumps(P24["proposal"])))
        for w in table:
            for k in (w.get("id"), w.get("name")):
                run.proposed_fields[str(k)] = json.loads(json.dumps(w))
        return run, table
    return make


def p24_counter(j2, run, table, workflows=None):
    """Priority's turn and Adaptation's ACCEPT: the reply expanded (_carry with the table shown), then the validator (_agree)."""
    wfs = run._carry(j2.norm(json.loads(json.dumps(workflows or P24["counter"]["workflows"]))), "Priority", table)
    run._agree(wfs, counter=True)
    return [m for m in run.chat if m["who"] == "validator"]


def test_p24_the_counter_of_run_4a9c_is_charged_6_7_5_and_adaptation_is_told_of_f10(j2hp, hp_run):
    run, table = hp_run()      # rate card off, as in the run: the same parts ["fix"] were charged 6, 7 and 5 (a card charges 8 each)
    said = p24_counter(j2hp, run, table)
    new = [w for w in run.workflows if w["id"] not in ("W-1", "W-2", "W-3")]
    assert [(w["id"], w["cost"], w["envelope"]["money_limit"]) for w in new] == [("W-4", 6, 6), ("W-5", 7, 7), ("W-6", 5, 5)], run.rejections
    assert all(w["fixes"] == ["D-3"] for w in new), [w["fixes"] for w in new]          # the proposal's, not the move's
    assert said[-1].get("charged") == 18 and "Budget: 90/100 used." in said[-1]["text"], said[-1]
    note = said[0]["text"]
    assert note.startswith("@Adaptation Priority also set ") and said[0].get("audience") == "adaptation", note
    for name in ("Fix unlabelled claims in roles and sourcing", "Fix unlabelled claims in selection, fairness and privacy",
                 "Fix unlabelled claim in onboarding"):
        assert f"fixes of '{name}' to [\"D-3\", \"F-10\"]" in note, note
    assert "atoms" not in note, note      # the move's atoms only lack the item numbers code tagged on the proposal
    assert "estimated_resources of 'Fix unlabelled claim in onboarding' to {\"money\": 5, \"calls\": 3, \"time_minutes\": 5}" in note, note
    assert "stays as you proposed it" in note, note
    assert not [f for f in run.__dict__.get("autofixes", []) if f["kind"] == "carried"], run.__dict__.get("autofixes")


def test_p24_a_counter_without_a_money_limit_is_rejected(j2hp, hp_run):
    run, table = hp_run()
    bare = [{k: v for k, v in w.items() if k != "envelope"} for w in P24["counter"]["workflows"]]
    p24_counter(j2hp, run, table, bare)
    assert [w["id"] for w in run.workflows] == ["W-1", "W-2", "W-3"] and run.spent == 72
    assert [r["reason"] for r in run.rejections] == ["a counter must state its money limit"] * 3, run.rejections


def test_p24_a_grant_without_a_money_limit_still_keeps_the_proposals_price(j2hp, hp_run):
    run, table = hp_run()
    bare = [{"id": w["id"]} for w in P24["counter"]["workflows"]]
    wfs, lost = run._kept_price(run._carry(j2hp.norm(bare), "Priority", table), table)
    assert not lost and [j2hp.granted(w) for w in wfs] == [8, 9, 7]


@pytest.mark.parametrize("limit, ok", [(7, False), (8, True), (9, True)])
def test_p24_with_the_rate_card_on_it_is_a_floor_never_the_price(j2hp, hp_run, limit, ok):
    run, table = hp_run({"fix": 8})
    run.p_refused = {}
    move = [{**w, "envelope": {**w["envelope"], "money_limit": limit}} for w in P24["counter"]["workflows"][:1]]
    p24_counter(j2hp, run, table, move)
    new = [w for w in run.workflows if w["id"] not in ("W-1", "W-2", "W-3")]
    if ok:
        assert [(w["cost"], w["envelope"]["money_limit"]) for w in new] == [(limit, limit)], (new, run.rejections)
    else:
        assert not new and [r["reason"] for r in run.rejections] == ["its money limit 7 is below its rate-card price 8 (fix), the floor"]


def test_p24_priority_is_asked_for_the_id_and_the_envelope_only(j2hp):
    fmt = j2hp.J2Run.PRICE_FMT
    assert json.loads(re.sub(r" \(the proposed workflow's id\)", "", fmt).replace("str", '"s"').replace("int", "0")) == \
        [{"id": "s", "envelope": {"money_limit": 0, "model_call_limit": 0, "time_limit_minutes": 0, "retry_limit": 0, "stop_loss": "s"}}]
    src = Path(j2hp.__file__).read_text(encoding="utf-8")
    assert src.count("self.PRICE_FMT") == 2 and "self.GRANT_FMT + ' (what you fund" not in src


# ---- P25 (D251): the budget cap only from J2_BUDGET_CAP; every raise is the Requester's own ------------------------------------
def test_p25_the_cap_comes_from_j2_budget_cap_only_when_it_is_set(tmp_path):
    with fresh_j2(tmp_path / "a", J2_BUDGET="100") as mod:
        assert mod.BUDGET_CAP is None and mod.budget_room(100) == float("inf")      # J2 made it twice the budget
    with fresh_j2(tmp_path / "b", J2_BUDGET="100", J2_BUDGET_CAP="150") as mod:
        assert mod.BUDGET_CAP == 150 and mod.budget_room(100) == 50


def test_p25_without_a_cap_a_raise_adds_all_and_its_option_names_no_most(j2, make_run, monkeypatch):
    monkeypatch.setattr(j2, "BUDGET_CAP", None)
    run = make_run()
    run.budget = 100
    run._raise_budget(500, "the Requester's answer")
    assert run.budget == 600 and j2.own_number(j2.budget_room(600)) == "Or type your own number"
    monkeypatch.setattr(j2, "BUDGET_CAP", 650)
    run._raise_budget(500, "the Requester's answer")
    assert run.budget == 650 and j2.own_number(j2.budget_room(600)) == "Or type your own number, up to 50"


LIMIT_Q = {"question": "Add more and keep going, or finish as it is?", "options": ["Add 30 work credits and keep going", "Finish as it is"],
           "budget": [30, 0]}


def test_p25_a_raise_question_shows_the_credits_approved_so_far(j2, make_run, monkeypatch):
    monkeypatch.setattr(j2, "BUDGET_CAP", None)
    run = make_run()
    run.budget = 100
    assert run._so_far() == "So far: 100 work credits approved."
    run._raise_budget(30, "the Requester's answer")
    assert run._so_far() == "So far: 100 + 30 = 130 work credits approved."
    run._ask_user("The work you approved is used up.", [dict(LIMIT_Q)], "limit", handoff={"kind": "limit", "choices": ["continue", "ship"]})
    assert run.paused["questions"][0]["question"].endswith(" So far: 100 + 30 = 130 work credits approved."), run.paused
    other = make_run()
    other._ask_user("Which one?", [{"question": "Which layout?", "options": ["A", "B"]}], "limit", handoff={"kind": "limit"})
    assert "So far" not in other.paused["questions"][0]["question"]          # a question that adds no credits shows no total
    asks = make_run()
    asks.budget = 100
    asks._ask_user("Over its envelope.", [{"question": "Run W-2 for 20 more?", "options": ["Yes", "No"]}], "approval")
    assert asks.paused["questions"][0]["question"].endswith(" So far: 100 work credits approved.")


@pytest.mark.parametrize("kind", ["approval", "ruling_budget"])
def test_p25_decide_for_me_never_approves_a_raise(j2, make_run, kind):
    run = make_run()
    run.auto = True
    run.paused = {"kind": kind, "questions": [{"question": "Add 20 work credits?", "options": []}], "handoff": {}, "msg": 1}
    assert run._auto_choice(run.paused)[0] == "Yes, approve it."          # still what the Simple view suggests
    assert run._auto_pick() is None                                     # but only the Requester answers it


def test_p25_decide_for_me_waits_on_a_limit_whose_pick_adds_credits_and_since_p29_on_every_limit(j2, make_run):
    run = make_run()
    run.auto = True
    run.paused = {"kind": "limit", "questions": [dict(LIMIT_Q)], "handoff": {"choices": ["continue", "ship"]}, "msg": 1}
    assert run._auto_pick() is None
    run.paused = {"kind": "limit", "questions": [{"question": "q", "options": ["Leave out the stories", "Finish as it is"]}],
                  "handoff": {"choices": ["drop", "ship"]}, "msg": 1}
    assert run._auto_pick() is None                                     # P29 (D431): a limit question is the Requester's own
    assert run._auto_choice(run.paused)[:2] == ("Option 1", "Leave out the stories")      # still what the Simple view suggests


# ---- P26 (D421, D422): dollar mode (J2_USD_BUDGET). Part 1: the run's cost from its AI calls --------------------------------------
def test_p26_call_usd_takes_the_reported_price_or_estimates_from_tokens(j2):
    assert j2.call_usd({"usd": 0.12, "tokens": {"input": 1000, "output": 10}}, None) == (0.12, False)      # reported
    assert j2.call_usd({"usd": 0.0, "tokens": {"input": 9, "output": 1}}, 1.0) == (0.0, False)             # a rate card's (or a free) price
    usd, est = j2.call_usd({"usd": None, "tokens": {"input": 900_000, "output": 100_000}}, 4e-6)            # at the run's own rate
    assert est is True and usd == pytest.approx(4.0)
    usd, est = j2.call_usd({"tokens": {"input": 900_000, "output": 100_000}}, None)                         # no priced call yet: fallback
    assert est is True and usd == pytest.approx(j2.USD_PER_MTOK_FALLBACK) and j2.USD_PER_MTOK_FALLBACK == 3.18
    usd, est = j2.call_usd({"tokens": None, "chars": {"prompt": 3_000_000, "reply": 1_000_000}}, None)        # mock: characters / 4
    assert est is True and usd == pytest.approx(3.18)


@pytest.mark.parametrize("x, text", [(20, "$20"), (20.4, "$20.40"), (1.25, "$1.25"), (0.004, "$0.01"), (0, "$0"), (10000, "$10,000")])
def test_p26_fmt_usd(j2, x, text):
    assert j2.fmt_usd(x) == text


@pytest.mark.parametrize("text, amount", [("Add $10 and keep going", 10.0), ("$12.50", 12.5), ("add 10 dollars", 10.0), ("Add $ 1,000 please", 1000.0),
                                          ("add 30", None), ("Option 1", None), ("", None)])
def test_p26_parse_usd(j2, text, amount):
    assert j2.parse_usd(text) == amount


def logged(run, j2, meta):
    from sutra_app.engine import llm
    llm.LAST_META.clear()
    llm.LAST_META.update(meta)
    return run._log_call("identity", "", "s" * 400, "u" * 400, "r" * 200, {}, 0.1)


def test_p26_cost_is_summed_from_reported_usd_and_unpriced_calls_are_estimated(tmp_path):
    with fresh_j2(tmp_path, J2_USD_BUDGET="20") as j2:
        assert (j2.USD_BUDGET, j2.USD_CAP) == (20.0, None)
        run = j2.J2Run(run_dir=tmp_path / "runs" / "j2-20261104-100001-7f3a")
        assert (run.usd_used, run.usd_limit, run.usd_raises, run.usd_estimated_calls) == (0.0, 20.0, [], 0)
        logged(run, j2, {"provider": "claude", "usd": 0.5, "input_tokens": 90_000, "output_tokens": 10_000})
        assert run.usd_used == pytest.approx(0.5) and run.usd_estimated_calls == 0
        rec = logged(run, j2, {"provider": "codex", "input_tokens": 18_000, "output_tokens": 2_000})          # no price: the run's $5 per million
        assert rec["usd_estimated"] is True and rec["usd_counted"] == pytest.approx(0.1)
        assert run.usd_used == pytest.approx(0.6) and run.usd_estimated_calls == 1 and run.usd_estimated_by == {"codex": 1}
        rows = [json.loads(line) for line in Path(run.dir, "calls.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [r.get("usd_counted") for r in rows] == [0.5, pytest.approx(0.1)] and rows[1]["usd_estimated"] is True
        assert run._usd_metrics() == {"usd": {"used": 0.6, "limit": 20.0, "approved": [20.0], "estimated_calls": 1}}


def test_p26_off_without_env_is_unchanged(j2, make_run):
    assert j2.USD_BUDGET is None
    run = make_run()
    rec = logged(run, j2, {"provider": "claude", "usd": 0.5, "input_tokens": 90_000, "output_tokens": 10_000})
    assert "usd_counted" not in rec and "usd_estimated" not in rec and run.usd_used == 0.0 and run._usd_metrics() == {}


# ---- P26 part 2 (D422): the dollar limit, credit top-ups by code, the dollar question ---------------------------------------------
@pytest.fixture
def usd_j2(tmp_path):
    with fresh_j2(tmp_path / "usd-env", J2_USD_BUDGET="20") as mod:
        yield mod


def usd_run(mod, tmp_path, name="j2-20261104-100009-7f3a"):
    return mod.J2Run(run_dir=tmp_path / "runs" / name)


def built_run(mod, tmp_path, name="j2-20261104-100011-7f3a"):
    """A run that has made the Brew Lab site in mock mode (a generous limit), then stands still: the handlers below need its
    output and charter."""
    run = usd_run(mod, tmp_path, name)
    run.usd_limit = 10_000.0
    say(run, BREW_LAB)
    run.paused, run.usd_used, run.usd_limit, run.usd_raises = None, 20.4, 20.0, []
    return run


def test_p26_starting_credits_follow_the_dollar_limit_and_j2_budget_is_ignored(tmp_path):
    with fresh_j2(tmp_path / "a", J2_USD_BUDGET="20", J2_BUDGET="100") as mod:
        assert mod.BUDGET == math.ceil(20 / mod.USD_PER_CREDIT) == 1070 and mod.USD_PER_CREDIT == 0.0187
        assert usd_run(mod, tmp_path).budget == 1070
    with fresh_j2(tmp_path / "b", J2_BUDGET="100") as mod:
        assert mod.BUDGET == 100 and mod.USD_BUDGET is None


def test_p26_top_up_follows_the_dollars_left_without_a_question(usd_j2, tmp_path):
    run = usd_run(usd_j2, tmp_path)
    run.budget, run.spent, run.usd_used = 10, 10, 19.9
    assert run._top_up(5) is True and run.budget == 15                      # $0.10 left buys 5 credits at $0.0187
    assert run.raises[-1] == {"cycle": 0, "asked": 5, "from": 10, "to": 15, "why": "code top-up from dollars left", "code": True}
    assert run._top_up(6) is False and run.budget == 15 and run.paused is None
    assert "Code added 5 work credits from the dollars left." in [m["text"] for m in run.chat]


def test_p26_approval_is_funded_by_code(usd_j2, tmp_path, monkeypatch):
    run = usd_run(usd_j2, tmp_path)
    w = {"id": "W-1", "name": "Menu", "cost": 50}
    monkeypatch.setattr(run, "_wf", lambda wid: w)
    run.budget, run.spent = 20, 0
    run._identity_approval({"wid": "W-1", "over": ["money 50 > 20"]})
    assert run.paused is None and run.turn == "priority" and run.handoff["kind"] == "envelope" and run.budget >= 50
    assert run.raises[-1]["code"] is True


def test_p26_ruling_over_budget_is_funded_by_code(usd_j2, tmp_path, monkeypatch):
    run = built_run(usd_j2, tmp_path)
    table = [{"id": "W-1", "name": "Menu", "cost": 50, "envelope": {"money_limit": 50, "model_call_limit": 2, "retry_limit": 1}}]
    c = {"id": "C-1", "identity": [{"say": "Build the menu."}], "pending_winner": "adaptation", "ruled_wfs": table}
    settled, agreed = [], []
    monkeypatch.setattr(run, "_conflict", lambda cid: c)
    monkeypatch.setattr(run, "_settle", lambda conflict, winner, note: settled.append((winner, note)))
    monkeypatch.setattr(run, "_agree", lambda wfs, counter=False: agreed.append(wfs))
    monkeypatch.setattr(run, "_save_conflicts", lambda: None)
    run.budget = run.spent = 10
    run.usd_used = 0.0
    run._priority_prices_ruling({"conflict": "C-1", "table": table})
    assert run.paused is None and agreed == [table] and settled[-1][0] == "adaptation"
    assert run.budget - run.spent >= 50 and run.raises[-1]["code"] is True


def test_p26_raise_from_need_at_run_ratio_half_without_need_and_cap_room(usd_j2, tmp_path, monkeypatch):
    run = usd_run(usd_j2, tmp_path)
    run.spent, run.usd_used = 100, 4.0                                       # $0.04 per credit in this run
    run.call_log = run.call_log + [{}] * usd_j2.USD_RATE_MIN_CALLS           # its own rate counts from its 8th call (R2-1)
    assert run._usd_raise(50) == 2.0
    assert run._usd_raise(None) == 10.0                                     # half of $20
    run.usd_limit = 31
    assert run._usd_raise(None) == 16.0                                     # above $10: to the dollar
    run.usd_limit, run.usd_used = 2, 2
    assert run._usd_raise(None) == 1.0                                      # never below $1
    monkeypatch.setattr(usd_j2, "USD_CAP", 25.0)
    run.usd_limit = 20
    assert run._usd_raise(None) == 5.0                                      # the cap's room
    run.usd_limit = 25
    assert run._usd_raise(None) == 0                                        # at the cap: no raise


def test_p26_no_cap_unless_set(usd_j2, tmp_path):
    assert usd_j2.USD_CAP is None
    run = usd_run(usd_j2, tmp_path)
    run._usd_add(5000, "Add $5000")
    assert run.usd_limit == 5020


USD_Q = {"question": "This run has used $20.40 of $20 (API price). Add $10? So far: $20 approved.",
         "options": ["Add $10 and keep going: you get more of the missing parts built. Or type your own amount", "Finish as it is: you get the site"],
         "budget": [10.0, 0]}


def answer_usd(run, text, q=None):
    h = {"kind": "requester_answered", "limit": "Dollar limit", "choices": ["continue", "ship"], "resume": None, "usd": True,
         "asked": [dict(q or USD_Q)], "answer": text}
    run._identity_hears_requester(h)


def test_p26_typed_over_5x_is_asked_back_and_a_click_confirms(usd_j2, tmp_path):
    run = built_run(usd_j2, tmp_path)
    answer_usd(run, "Add $150 and keep going")
    p = run.paused
    assert p and p["kind"] == "limit" and run.usd_limit == 20 and run.usd_raises == []
    assert p["questions"][0]["question"].startswith("This run has used $20.40 of $20 (API price). Add $150? So far: $20 approved.")
    assert p["questions"][0]["options"][0].startswith("Add $150 and keep going") and p["questions"][0]["budget"][0] == 150
    said = [m["text"] for m in run.chat if m.get("who") == "identity"][-1]
    assert "You typed $150, more than 5 times this run's limit of $20. Pick it to confirm, or choose another option." in said
    assert p["handoff"]["usd"] is True
    run.paused = None
    answer_usd(run, "Option 1", p["questions"][0])                          # a click is never checked
    assert run.usd_limit == 170 and len(run.usd_raises) == 1


def test_p26_typed_under_5x_is_applied_and_the_model_add_is_ignored(usd_j2, tmp_path):
    run = built_run(usd_j2, tmp_path)
    answer_usd(run, "Add $30 and keep going")
    assert run.usd_limit == 50 and run.usd_raises[0]["from"] == 20 and run.usd_raises[0]["to"] == 50
    assert run._usd_so_far().startswith("So far: $20 + $30 = $50 approved.")
    other = built_run(usd_j2, tmp_path, "j2-20261104-100010-7f3a")
    answer_usd(other, "add 30")                                             # no dollar amount: the option's own $10
    assert other.usd_limit == 30


def test_p26_estimated_calls_are_named(usd_j2, tmp_path):
    run = usd_run(usd_j2, tmp_path)
    run.usd_estimated_calls, run.usd_estimated_by = 3, {"codex": 3}
    assert run._so_far() == "So far: $20 approved. 3 calls estimated: Codex reports no price."


def test_p26_decide_for_me_never_answers_the_dollar_question(usd_j2, tmp_path):
    run = usd_run(usd_j2, tmp_path)
    run.auto = True
    run.paused = {"kind": "limit", "questions": [dict(USD_Q)], "handoff": {"choices": ["continue", "ship"], "usd": True}, "msg": 1}
    assert run._auto_pick() is None and run.snapshot()["paused"]["auto_waits"] is True


def test_p26_spec_fields_bounds_and_old_credit_keys(tmp_path):
    from pydantic import ValidationError
    from sutra_app.engine.spec import EngineSettings
    s = EngineSettings()
    assert (s.usd_budget, s.usd_cap) == (20.0, None) and s.to_env()["J2_USD_BUDGET"] == "20.0" and "J2_USD_CAP" not in s.to_env()
    assert EngineSettings(usd_budget=12.5, usd_cap=100).to_env()["J2_USD_CAP"] == "100.0"
    for bad in ({"usd_budget": 0.5}, {"usd_budget": 10_001}, {"usd_cap": 0}, {"usd_budget": float("nan")}):
        with pytest.raises(ValidationError):
            EngineSettings(**bad)
    assert EngineSettings(budget=250, budget_cap=500, limit_add=40).budget == 250       # stored credit settings stay valid


# ---- P28 (D431): the same build failure twice in a row, across workflows, stops the cycle -------------------------------------
# Beta run j2-20261118-071410-17e1 (Bean There): every builder failed with "changed outside its folder: agent_live.json,
# events.jsonl, snapshot.json", and Adaptation replaced the failed workflow six times (W-1, W-6, W-7, W-11, W-12, W-13).
OUTSIDE_17E1 = ["agent_live.json", "events.jsonl", "snapshot.json"]


def failed_receipts(*pairs, text="a check"):
    """A built workflow whose one atom's latest receipts fail with these (type, evidence) pairs; `text` is the check's own wording."""
    return [{"id": "a1", "results": [{"check": f"{text} {n}", "type": t, "evidence": e, "pass": False}
                                     for n, (t, e) in enumerate(pairs)] + [{"check": "ok", "type": "file-exists", "evidence": "x", "pass": True}]}]


def test_p28_build_failure_outside_write_in_any_order_is_the_same_and_another_file_set_is_not(j2):
    one = {"id": "W-1", "name": "Write the exact copy sheet", "status": "failed", "failure": ["outside_write", list(OUTSIDE_17E1)]}
    six = {"id": "W-6", "name": "Write the copy sheet again", "status": "failed", "failure": ["outside_write", OUTSIDE_17E1[::-1]]}
    other = {"id": "W-7", "name": "Write the exact copy sheet", "status": "failed", "failure": ["outside_write", ["notes.txt"]]}
    assert j2.build_failure(one) == j2.build_failure(six) == ("outside_write", tuple(OUTSIDE_17E1))
    assert j2.build_failure(other) != j2.build_failure(one)          # the same name, another cause: not the same failure


def test_p28_build_failure_of_failed_checks_reads_type_and_evidence_never_the_name_or_check_text(j2):
    a = {"id": "W-2", "name": "Build the menu", "status": "done", "atoms": failed_receipts(("file-exists", "index.html not found"))}
    b = {"id": "W-5", "name": "Rebuild the menu section", "status": "done",
         "atoms": failed_receipts(("file-exists", "index.html not found"), text="the menu page is there")}
    c = {**b, "atoms": failed_receipts(("file-exists", "menu.html not found"))}
    assert j2.build_failure(a) == j2.build_failure(b) == ("checks", (("file-exists", "index.html not found"),))
    assert j2.build_failure(c) != j2.build_failure(a)


def test_p28_build_failure_is_none_for_a_pass_and_failed_for_a_record_from_before(j2):
    passed = {"id": "W-3", "status": "done", "atoms": [{"id": "a1", "results": [{"type": "file-exists", "evidence": "x", "pass": True}]}]}
    assert j2.build_failure(passed) is None and j2.build_failure({"id": "W-4", "status": "registered"}) is None
    assert j2.build_failure({"id": "W-1", "status": "failed"}) == ("failed", "")


def test_p28_a_builder_tool_fault_keeps_every_outside_file_sorted(j2, make_run):
    assert j2.BuilderToolFault("outside", "x", files=["b", "a"]).files == ["a", "b"]
    assert j2.BuilderToolFault("limits", "x").files == []
    run = make_run()
    run.post("user", "go")
    names = {f"n{i}.txt": "x" for i in range(7)}                     # the message names 5 of them; the fault keeps all 7
    with pytest.raises(j2.BuilderToolFault) as e:
        tools_call(j2, run, extra=names)
    assert e.value.files == sorted(names) and "and 2 more" in str(e.value)


DONE_17E1 = ["The page shows the business name Bean There and its address 12 Park Road.",
             "The page shows the opening hours 7am-6pm daily.",
             "The page shows a menu listing espresso £2.50, flat white £3.20 and croissant £2.80.",
             "The page has no JavaScript errors, no horizontal overflow at 360px and 1280px, and every in-page link points to an "
             "existing section."]


@pytest.fixture
def replay_17e1(j2, make_run, monkeypatch):
    """Replay A: run 17e1's website run (4 done-when items, 100 credits) with builder tools on. A build whose `fault` entry
    is a file list fails as the run's builders did (the CLI wrote those files outside its folder); None builds and passes.
    Returns (run, add, fault, builder_calls)."""
    run = make_run()
    run.post("user", "A one-page website for Bean There")
    run._apply_output("website")
    run.goal, run.budget = {"statement": "Bean There", "done_when": list(DONE_17E1)}, 100
    cwd = Path(run.dir) / "out"
    cwd.mkdir(parents=True, exist_ok=True)
    tools = {"tools": ["Write"], "allow": ["Write"], "cwd": str(cwd), "root": str(run.dir), "usd": 1.0, "log_chars": 200,
             "max_files": 50, "max_bytes": 1_000_000}
    monkeypatch.setattr(run, "_builder_tools", lambda: tools)
    fault, builder_calls, real_call = {"files": list(OUTSIDE_17E1)}, [], run.call

    def call(fn, fmt, task, mock, **kw):
        if not str(fn).startswith("W-"):
            return real_call(fn, fmt, task, mock, **kw)
        builder_calls.append(fn)
        if fault["files"] is None:
            (cwd / run._main_file()).write_text("<!doctype html><title>Bean There</title><main>Bean There</main>")
            return {"say": "built", "human_output": "I built it.", "atom_human_output": "Built."}
        files = fault["files"]
        raise j2.BuilderToolFault("outside", "changed outside its folder: " + ", ".join(files), files=files)
    monkeypatch.setattr(run, "call", call)

    def add(wid, name, cost=6, checks=(), **kw):
        j2.add_workflow_agent(wid)
        w = {"id": wid, "name": name, "section": wid, "status": "registered", "cost": cost, "charged": True, "cycle": 1,
             "envelope": {"money_limit": cost, "model_call_limit": 2, "retry_limit": 1}, "calls_used": 0, "retries_used": 0,
             "outputs": ["copy.md"], "covers": [], "covers_text": [], "dependencies": [], "kind": "build",
             "atoms": [{"id": f"{wid}.a1", "goal": name, "verification": list(checks)}], **kw}
        run.workflows.append(w)
        run._recalc_spent()
        return w
    return run, add, fault, builder_calls


def test_p28_replay_17e1_stops_after_the_second_identical_failure(replay_17e1):
    run, add, fault, calls = replay_17e1
    add("W-1", "Write the exact copy sheet")
    run._turn_workflow_agent({"wid": "W-1"})
    assert run.turn == "coordination" and run._wf("W-1")["failure"] == ["outside_write", OUTSIDE_17E1]
    add("W-6", "Write the exact copy sheet", replaces="W-1")       # Adaptation's reworded replacement
    run._turn_workflow_agent({"wid": "W-6"})
    assert run.turn == "identity" and run.handoff["kind"] == "limit", run.handoff
    assert run.handoff["reason"] == ("The same failure came back twice in a row: W-1 and W-6 both failed (changed files outside "
                                     "its folder: agent_live.json, events.jsonl, snapshot.json), so another attempt would likely "
                                     "repeat it.")
    assert calls == ["W-1", "W-6"] and run.spent == 12 and run.repeat_steps == ["W-1", "W-6"]
    assert [e for e in run.events if e["type"] == "repeat" and "W-1 and W-6" in json.dumps(e)]


def test_p28_a_different_file_set_is_not_the_same_failure(replay_17e1):
    run, add, fault, _ = replay_17e1
    add("W-1", "Write the exact copy sheet")
    run._turn_workflow_agent({"wid": "W-1"})
    fault["files"] = ["notes.txt"]
    add("W-6", "Write the exact copy sheet", replaces="W-1")
    run._turn_workflow_agent({"wid": "W-6"})
    assert run.turn == "coordination" and run.repeat_steps == []


def test_p28_a_passing_build_in_between_clears_it(replay_17e1):
    run, add, fault, _ = replay_17e1
    add("W-1", "Write the exact copy sheet")
    run._turn_workflow_agent({"wid": "W-1"})
    fault["files"] = None
    add("W-2", "Build the page base")
    run._turn_workflow_agent({"wid": "W-2"})
    assert run._wf("W-2")["status"] == "done" and run.last_failure is None
    fault["files"] = list(OUTSIDE_17E1)
    add("W-6", "Write the exact copy sheet", replaces="W-1")
    run._turn_workflow_agent({"wid": "W-6"})
    assert run.turn == "coordination", run.handoff


def test_p28_the_same_failed_checks_across_reworded_workflows_stop_and_keep_going_resumes_atom_failed(replay_17e1):
    run, add, fault, _ = replay_17e1
    fault["files"] = None                                            # both build, and the same check fails on the same evidence
    menu = {"type": "file-exists", "target": "menu.html", "expect": True}
    add("W-4", "Build the menu section", checks=[{**menu, "text": "The menu page is there"}])
    run._turn_workflow_agent({"wid": "W-4"})
    assert run.turn == "adaptation" and run.handoff["kind"] == "atom_failed"
    add("W-9", "Build the menu section from the charter", checks=[{**menu, "text": "menu.html exists in the folder"}])
    run._turn_workflow_agent({"wid": "W-9"})
    assert run.turn == "identity" and run.handoff["kind"] == "limit", run.handoff
    assert run.handoff["reason"].startswith("The same failure came back twice in a row: W-4 and W-9 both failed (the same "
                                            "checks failed: file-exists: ")
    assert run.handoff["resume"]["to"] == "adaptation" and run.handoff["resume"]["handoff"]["kind"] == "atom_failed"
    assert run.handoff["resume"]["handoff"]["wid"] == "W-9"


def test_p28_a_keep_going_answer_does_not_clear_the_memory(replay_17e1):
    """OQ-1: "keep going" changes nothing about the cause, so the next identical failure asks again (run 17e1 went on to
    W-12 and W-13 after "Option 1")."""
    run, add, fault, calls = replay_17e1
    for wid in ("W-1", "W-6"):
        add(wid, "Write the exact copy sheet")
        run._turn_workflow_agent({"wid": wid})
    run._identity_limit(run.handoff)
    p = run.paused
    assert p and p["kind"] == "limit" and p["handoff"]["choices"][0] == "continue", p
    run.paused = None
    run._identity_hears_requester({**p["handoff"], "asked": p["questions"], "answer": "Option 1"})
    add("W-11", "Build the page base and intro from the charter", outputs=["index.html"])
    run._turn_workflow_agent({"wid": "W-11"})
    assert run.turn == "identity" and run.handoff["kind"] == "limit" and "W-6 and W-11" in run.handoff["reason"], run.handoff
    assert calls == ["W-1", "W-6", "W-11"]


def copy_sheet(cause=None, **kw):
    """A proposal after Replay A: by default the page base again, covering item 1 as the repeated step did, and writing
    index.html as nearly every page workflow does."""
    atom = {"id": "a1", "goal": "write the page base", "context": ["charter"], "constraints": ["only the folder"],
            "how": {"kind": "AI", "agent": "Builder", "steps": "write index.html"},
            "expected_output": [{"text": "index.html exists", "kind": "file", "target": "index.html"}],
            "verification": [{"text": "index.html exists", "type": "file-exists", "target": "index.html", "expect": True}]}
    return {"name": "Build the page base into the output folder", "kind": "build", "goal_gap": "the page base",
            "outputs": ["index.html"], "completion_check": "index.html exists", "covers": [1], "dependencies": [], "atoms": [atom],
            "parts": ["page_section"], "cost": 10, **({"cause_change": cause} if cause is not None else {}), **kw}


def repeated(replay_17e1):
    """Replay A on the page base (run 17e1's W-7 and W-11: covers item 1, writes index.html)."""
    run, add, fault, calls = replay_17e1
    for wid in ("W-1", "W-6"):
        add(wid, "Build the page base and intro from the charter", covers=[1], covers_text=[DONE_17E1[0]], outputs=["index.html"])
        run._turn_workflow_agent({"wid": wid})
    assert run.repeat_steps == ["W-1", "W-6"]
    return run


def test_p28_a_redo_of_a_repeated_step_without_cause_change_is_rejected(replay_17e1):
    run = repeated(replay_17e1)
    why = ("it redoes W-1 and W-6, which failed the same way twice, and its cause_change is empty: say what is different about "
           "the cause this time")
    for cause in (None, "", "  "):                                    # it covers their item 1
        reg, refused, _ = run._register([copy_sheet(cause)])
        assert not reg and refused == [f"Build the page base into the output folder ({why})"], refused
    reg, refused, _ = run._register([copy_sheet(replaces=["W-6"], covers=[], outputs=["copy.md"], parts=["styling"], cost=5)])
    assert not reg and "(it redoes W-6, which failed the same way twice, and its cause_change is empty" in refused[0], refused
    reg, refused, _ = run._register([copy_sheet("write the page into out/, not the run folder")])
    assert [w["name"] for w in reg] == ["Build the page base into the output folder"] and not refused, refused
    assert reg[0]["cause_change"] == "write the page into out/, not the run folder"


def test_p28_a_proposal_for_other_items_needs_no_cause_change_even_when_it_writes_the_same_file(replay_17e1):
    """Owner's follow-up to D431: only replacing the failed workflow or covering its items is a redo; sharing index.html,
    which nearly every page workflow writes, is not."""
    run = repeated(replay_17e1)
    menu = copy_sheet(name="Build the menu section", covers=[3])                  # outputs ["index.html"], like W-1 and W-6
    reg, refused, _ = run._register([menu])
    assert [w["name"] for w in reg] == ["Build the menu section"] and not refused, refused
    assert "cause_change" not in reg[0]


def test_p28_the_prompt_lines_appear_only_after_a_repeat(replay_17e1, monkeypatch):
    run, add, fault, calls = replay_17e1
    seen = {}

    class Seen(Exception):
        pass

    def spy(fn, fmt, task, mock, **kw):
        seen[fn] = task
        raise Seen
    table = [{**copy_sheet("write the copy into out/"), "id": "p1"}]      # it covers item 1, as W-1 and W-6 did

    def prompts():
        seen.clear()
        with monkeypatch.context() as mp:
            mp.setattr(run, "call", spy)
            for turn, h in ((run._turn_adaptation, {"kind": "propose", "why": "x"}), (run._turn_priority, {"kind": "price", "table": table})):
                with pytest.raises(Seen):
                    turn(h)
        return seen["adaptation"], seen["priority"]
    adapt, prio = prompts()
    assert "cause_change" not in adapt and "cause_change" not in prio.split("ON THE TABLE")[1].split("]")[-1]
    assert "FAILED THE SAME WAY TWICE" not in adapt + prio
    for wid in ("W-1", "W-6"):
        add(wid, "Build the page base and intro from the charter", covers=[1], covers_text=[DONE_17E1[0]], outputs=["index.html"])
        run._turn_workflow_agent({"wid": wid})
    adapt, prio = prompts()
    assert ("W-1 and W-6 failed the same way twice (changed files outside its folder: agent_live.json, events.jsonl, "
            "snapshot.json)") in adapt and '"cause_change"' in adapt and "the validator rejects it" in adapt
    assert ('REDOES A STEP THAT FAILED THE SAME WAY TWICE: {"p1": "write the copy into out/"}. If a cause_change names '
            "nothing new about the cause, the money buys the same failure: REFUSE it with that reason.") in prio


# ---- P29 (D431): with nothing built, no option that leaves nothing to build, and never Done ---------------------------------------
# Replay B: run 17e1's [81]-[90]. No site, the 4 items, one audit at version 0 failing them, 100 of 100 credits spent; Identity's
# question offered "Leave out" all four items, "Option 2" was picked, and Identity then declared the run done with no site.
def audit_v0(crit, failing, output="website", version=0):
    return {"cycle": 1, "version": version, "output": output, "rubric": [], "conditions": [], "all_pass": not failing,
            "mechanical": {"available": False, "note": "nothing was built"},
            "results": [{"id": f"F-{i}", "item": i, "criterion": c, "pass": c not in failing,
                         "verdict": "FAIL" if c in failing else "PASS", "note": ""} for i, c in enumerate(crit, 1)]}


@pytest.fixture
def nothing_built(make_run):
    def make(failing=DONE_17E1):
        run = make_run()
        run.post("user", "A one-page website for Bean There")
        run._apply_output("website")
        run.goal, run.budget, run.spent = {"statement": "Bean There", "done_when": list(DONE_17E1)}, 100, 100
        run.audits = [audit_v0(DONE_17E1, failing)]
        assert not run.sites
        run._identity_limit({"reason": "The same failure came back twice in a row, so another cycle would likely repeat it."})
        return run
    return make


def test_p29_replay_17e1_offers_no_leave_out_that_leaves_nothing_with_nothing_built(nothing_built):
    run = nothing_built()
    h, opts = run.paused["handoff"], run.paused["questions"][0]["options"]
    assert "drop" not in h["choices"], (h["choices"], opts)
    assert not [o for o in opts if o.startswith("Finish as it is")]
    assert h["choices"] == ["continue", "ship"] and opts[-1] == "Stop here: nothing is built yet, so you get no site", opts


def test_p29_a_partial_leave_out_is_still_offered(nothing_built):
    """OQ-4: narrowing the scope is not shipping as is."""
    run = nothing_built(failing=[DONE_17E1[2]])
    h = run.paused["handoff"]
    assert "drop" in h["choices"] and h["drop_texts"] == [DONE_17E1[2]], h


def test_p29_leaving_everything_out_with_nothing_built_stops_never_done(nothing_built, monkeypatch):
    run = nothing_built(failing=[DONE_17E1[2]])
    p, real = run.paused, run.call
    monkeypatch.setattr(run, "call", lambda fn, *a, **kw: {"decision": "drop", "drop_items": [1, 2, 3, 4], "to_requester": "Sure.",
                                                           "to_agents": "", "confirmed": [], "still_to_be_confirmed": []}
                        if fn == "identity" else real(fn, *a, **kw))
    run.paused = None
    run._identity_hears_requester({**p["handoff"], "asked": p["questions"], "answer": "Leave all of it out"})
    assert re.fullmatch(r"Stopped on the Requester's decision \(.*\): nothing was built\.", run.outcome or ""), run.outcome
    assert run.goal["done_when"] == DONE_17E1 and run.turn is None
    assert run.last_limit["decision"] == "stop"
    run._write_summary()
    assert json.loads((Path(run.dir) / "summary.json").read_text())["status"] == "stopped"
    from sutra_app.orchestrator.stopwords import plain_outcome
    assert plain_outcome(run.outcome) == "It stopped: nothing was built."


def test_p29_workable_is_false_for_an_audit_at_version_0_and_unchanged_without_a_version(j2):
    a = audit_v0(DONE_17E1, [], output="prd")
    assert j2.workable(a) == ["nothing has been built yet"]
    old = {k: v for k, v in a.items() if k != "version"}
    assert j2.workable(old) == [] and j2.workable({**a, "version": 1}) == []


def test_p29_identity_cannot_declare_a_document_done_with_nothing_built(make_run, monkeypatch):
    run = make_run()
    run.post("user", "A PRD for Bean There")
    run._apply_output("prd")
    crit = ["The PRD names the users.", "The PRD lists the goals."]
    run.goal, run.budget, run.spent = {"statement": "PRD", "done_when": crit}, 100, 0
    run.audits = [audit_v0(crit, [], output="prd")]
    real = run.call
    monkeypatch.setattr(run, "call", lambda fn, *a, **kw: {"to_requester": "Your PRD is ready.", "to_agents": "", "done": True,
                                                           "clause": "done_when", "next": "Requester"}
                        if fn == "identity" else real(fn, *a, **kw))
    run._identity_audit({})
    assert run.turn == "adaptation" and not str(run.outcome or "").startswith("Done"), (run.turn, run.outcome)


def test_p29_decide_for_me_never_answers_a_limit_question_nor_the_repeat_question(replay_17e1, nothing_built):
    """Decide for me answered a second limit question with its last option (run 17e1: drop everything with nothing built).
    A limit question, the P28 repeat question among them, waits for the Requester, as the dollar question does (P26)."""
    run, add, fault, _ = replay_17e1
    for wid in ("W-1", "W-6"):
        add(wid, "Write the exact copy sheet")
        run._turn_workflow_agent({"wid": wid})
    run._identity_limit(run.handoff)
    run.auto = True
    assert run.paused["kind"] == "limit" and run._auto_pick() is None and run.snapshot()["paused"]["auto_waits"] is True
    second = nothing_built(failing=[DONE_17E1[2]])
    second.auto, second.auto_log = True, [{"kind": "limit"}]       # a second limit question: it took the last option
    assert second._auto_pick() is None and second.snapshot()["paused"]["auto_waits"] is True
    second.paused = {"kind": "limit", "questions": [{"question": "q", "options": ["Leave out the stories", "Finish as it is"]}],
                     "handoff": {"choices": ["drop", "ship"]}, "msg": 1}
    assert second._auto_pick() is None


# ---- P29 (D431, follow-up): the same necessary condition unmet for the same reason in two audits in a row stops the cycle ---------
# Beta run j2-20261123-103238-3429 (Pulse, 23 Nov): the charter listed no files and no test, so the gate conditions C1 ("the
# charter lists no files") and C2 ("the test '' is not a file in the folder") failed in every audit while the done-when results
# moved, and the run kept building. The run's folder is not on this Mac: the audits are rebuilt from that description, with the
# conditions' evidence made by code (_conditions on the folder) as in the run.
PULSE_DONE_WHEN = ["pulse.py prints the CPU and memory use every second.", "test_pulse.py checks pulse.py's output format and passes."]


@pytest.fixture
def pulse_run(j2ft, tmp_path):
    def make():
        run = j2ft.J2Run(run_dir=tmp_path / "runs" / "j2-20261123-103238-3429")
        run.post("user", "Build pulse.py, a tiny system monitor, with a test")
        run._apply_output(FT)
        run.goal, run.budget, run.spent = {"statement": "Pulse", "done_when": list(PULSE_DONE_WHEN)}, 100, 40      # no files, no test
        os.makedirs(run._out_dir(), exist_ok=True)
        (Path(run._out_dir()) / "pulse.py").write_text("print('cpu 3% mem 41%')\n")
        run.sites = ["pulse.py"]
        return run
    return make


def pulse_audit(run, cycle, failing):
    conds = run._conditions("pulse.py")
    return {"cycle": cycle, "version": len(run.sites), "output": run.output, "rubric": [], "conditions": conds, "all_pass": False,
            "mechanical": {},
            "results": [{"id": f"F-{i}", "item": i, "criterion": c, "pass": c not in failing, "verdict": "FAIL" if c in failing else "PASS",
                         "note": ""} for i, c in enumerate(PULSE_DONE_WHEN, 1)]}


def test_p29_replay_3429_the_same_unmet_condition_twice_in_a_row_asks_the_requester(pulse_run):
    run = pulse_run()
    first = pulse_audit(run, 1, [PULSE_DONE_WHEN[1]])
    assert {c["id"]: c["evidence"] for c in first["conditions"] if not c["met"]} == {
        "C1": "the charter lists no files",
        "C2": "code reran the test itself, on a copy of the folder, not the builder's own run: the test '' is not a file in the folder"}
    run.audits = [first]
    run._identity_audit({})
    assert run.turn == "adaptation" and not run.paused                   # once is not twice
    run.audits.append(pulse_audit(run, 2, [PULSE_DONE_WHEN[0]]))          # the done-when results moved; C1 and C2 did not
    run._identity_audit({})
    assert run.paused and run.paused["kind"] == "limit", (run.turn, run.handoff)
    assert run.paused["handoff"]["limit"] == ("This condition comes from the charter, and building can't change it. The charter "
                                              "needs fixing.")
    run.auto = True
    assert run._auto_pick() is None and run.snapshot()["paused"]["auto_waits"] is True      # Addition A: it waits for the Requester


def test_p29_the_same_condition_with_another_reason_is_not_the_same_failure(pulse_run):
    run = pulse_run()
    first = pulse_audit(run, 1, [PULSE_DONE_WHEN[1]])
    run.goal.update(files=["pulse.py", "test_pulse.py"], test=["test_pulse.py"])      # the charter now lists them: new reasons
    second = pulse_audit(run, 2, [PULSE_DONE_WHEN[0]])
    unmet = {c["id"]: c["evidence"] for c in second["conditions"] if not c["met"]}
    assert unmet["C1"] == "missing: test_pulse.py" and unmet["C2"].endswith("the test 'test_pulse.py' is not a file in the folder")
    run.audits = [first, second]
    run._identity_audit({})
    assert run.turn == "adaptation" and not run.paused, run.paused


def test_p29_a_buildable_condition_unmet_the_same_way_twice_goes_back_to_adaptation(make_run):
    """Review R1-1: only a condition the charter decides asks the Requester. A website's in-page link (N4) is the build's
    to fix: unmet for the same reason in two audits, it goes back to Adaptation as before."""
    run = make_run()
    run.post("user", "A one-page website")
    run._apply_output("website")
    crit = ["The page shows the name.", "The page shows the hours."]
    run.goal, run.budget, run.spent = {"statement": "x", "done_when": list(crit)}, 100, 20
    run.sites = ["<!doctype html><title>x</title>", "<!doctype html><title>y</title>"]

    def audit(failing, version):
        return {"cycle": 1, "version": version, "output": "website", "rubric": [], "all_pass": False,
                "mechanical": {"available": True, "js_errors": [], "broken_in_page_links": []},
                "conditions": [{"id": "N4", "text": "Every in-page link resolves", "check": "links-well-formed", "met": False,
                                "evidence": "broken in-page link: #menu"}],
                "results": [{"id": f"F-{i}", "item": i, "criterion": c, "pass": c not in failing,
                             "verdict": "FAIL" if c in failing else "PASS", "note": ""} for i, c in enumerate(crit, 1)]}
    run.audits = [audit([crit[0]], 1), audit([crit[1]], 2)]
    run._identity_audit({})
    assert run.turn == "adaptation" and not run.paused, (run.paused or {}).get("handoff")


def test_p29_with_nothing_built_a_lone_stop_here_is_asked_never_applied(make_run):
    """Review R1-3: nothing built and "keep going" can't be offered again (the last "keep going" changed nothing), so
    "Stop here" is the only option. The Requester is still asked; the run does not end, and Decide for me waits."""
    run = make_run()
    run.post("user", "A one-page website for Bean There")
    run._apply_output("website")
    run.goal, run.budget, run.spent = {"statement": "Bean There", "done_when": list(DONE_17E1)}, 100, 40
    run.audits = [audit_v0(DONE_17E1, DONE_17E1)]
    run.last_limit = {"state": (len(run.sites), len(run.workflows), run.spent), "decision": "continue"}
    run._identity_limit({"reason": "The same failure came back twice in a row, so another cycle would likely repeat it."})
    assert run.paused and run.paused["kind"] == "limit", run.outcome
    assert run.paused["handoff"]["choices"] == ["ship"]
    assert run.paused["questions"][0]["options"] == ["Stop here: nothing is built yet, so you get no site"]
    assert not str(run.outcome or "").startswith("Stopped")
    run.auto = True
    assert run._auto_pick() is None and run.snapshot()["paused"]["auto_waits"] is True


def test_p28_keep_going_after_a_repeat_stop_builds_the_waiting_queue(replay_17e1):
    """Review R1-5: when the stopped build had handed back to Coordination and other workflows wait, "keep going" resumes
    there and builds them, as P22's repeat does, instead of a fresh Adaptation cycle."""
    run, add, fault, calls = replay_17e1
    add("W-2", "Build the opening hours section", covers=[2], covers_text=[DONE_17E1[1]], outputs=["index.html"])     # waits
    for wid in ("W-1", "W-6"):
        add(wid, "Write the exact copy sheet")
        run._turn_workflow_agent({"wid": wid})
    assert run.handoff["kind"] == "limit" and run.handoff["resume"] == {"to": "coordination", "handoff": {"kind": "schedule"}}
    run._identity_limit(run.handoff)
    p = run.paused
    run.paused = None
    run._identity_hears_requester({**p["handoff"], "asked": p["questions"], "answer": "Option 1"})
    assert run.turn == "coordination" and run.handoff["kind"] == "schedule", (run.turn, run.handoff)


def test_p22_every_rejection_path_in_the_validator_sets_its_own_key():
    """D431 (R1-2 follow-up): every rejection carries a key set by code, distinct per rule, so a rule added later without
    one fails here instead of sharing another rule's bucket. Derived from the code, not from a hand-kept list:
    - every `self._reject(...)` call in j2.py passes a third argument, the key: a tuple literal naming its rule, or the
      rule chain's `key`;
    - in `_register`, `key_rules` has one entry per test of the reason chain (`reason = (... if ... else ...) or
      (budget)`), with the same test, in the same order (plus `over_budget` for the `or` tail);
    - the rule names are distinct across all of them."""
    import ast
    src = (Path(__file__).resolve().parents[2] / "sutra_app" / "engine" / "j2.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "_reject"]
    assert len(calls) >= 7, len(calls)
    names = []
    for c in calls:
        assert len(c.args) == 3, f"line {c.lineno}: _reject without a key"
        k = c.args[2]
        if isinstance(k, ast.Name):
            assert k.id == "key", f"line {c.lineno}: key {k.id}"
            continue
        assert isinstance(k, ast.Tuple) and k.elts and isinstance(k.elts[0], ast.Constant) and isinstance(k.elts[0].value, str) \
            and k.elts[0].value, f"line {c.lineno}: the key must be a tuple naming its rule"
        names.append(k.elts[0].value)
    reg = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_register")
    chain = next(n.value for n in ast.walk(reg) if isinstance(n, ast.Assign) and [getattr(t, "id", None) for t in n.targets] == ["reason"]
                 and isinstance(n.value, ast.BoolOp))
    tests, node = [], chain.values[0]
    while isinstance(node, ast.IfExp):
        tests.append(ast.dump(node.test))
        node = node.orelse
    entries = next(n.value for n in ast.walk(reg) if isinstance(n, ast.Assign)
                   and [getattr(t, "id", None) for t in n.targets] == ["key_rules"]).elts
    rules = [(e.elts[0].elts[0].value, ast.dump(e.elts[1])) for e in entries]
    assert [t for r, t in rules if r != "over_budget"] == tests, "the key list must follow the reason chain test by test"
    assert "over_budget" in [r for r, _ in rules] and len(tests) >= 17
    names += [r for r, _ in rules]
    assert len(names) == len(set(names)), sorted(x for x in names if names.count(x) > 1)


# ---- P30 (D433): every done-when item has a runnable check and a builder-set status; Done only when all are built and pass
MORNING = ["The tool lists new files every morning.", "The summary is posted to the team channel.", "The list names each file's size."]


def recording(run, monkeypatch, who):
    """run.call recorded for the functions `who` accepts (fmt, task), passed through to J2's mock."""
    seen, real = [], run.call
    monkeypatch.setattr(run, "call", lambda fn, *a, **kw: (seen.append((fn, a[0], a[1])) if who(fn) else None) or real(fn, *a, **kw))
    return seen


def intake(run, monkeypatch, done_when, checks, **h):
    """Identity's intake with a charter and item_checks of the test's own (no facts, so the fact check passes)."""
    real = run.call
    monkeypatch.setattr(run, "call", lambda fn, *a, **kw: {"to_requester": "Thanks, starting now.", "to_agents": "@Adaptation Charter.",
                                                           "enough": True, "next": "Adaptation", "item_checks": checks,
                                                           "goal": {"statement": "A morning file list", "site_name": "Morning",
                                                                    "done_when": list(done_when)}}
                        if fn == "identity" else real(fn, *a, **kw))
    run._identity_intake({"kind": "intake", **h})


@pytest.fixture
def site_run(make_run):
    run = make_run()
    run.post("user", "A one-page website that lists new files every morning")
    run.request = "A one-page website that lists new files every morning"
    run._apply_output("website")
    return run


def test_p30_intake_stores_a_check_per_item_by_text(j2, make_run, site_run, monkeypatch):
    run = make_run()
    say(run, BREW_LAB)
    g = run.goal
    assert set(g["item_checks"]) == set(g["done_when"])
    assert all(set(c) <= {"type", "target", "expect"} for c in g["item_checks"].values())
    # a change request keeps the checks of the items that stay (Identity's new list has the wrong length: none of it is taken)
    fe = {"type": "file-exists", "target": "index.html", "expect": True, "extra": "dropped"}
    intake(site_run, monkeypatch, MORNING, [fe] * 3)
    assert site_run.goal["item_checks"] == {t: {k: v for k, v in fe.items() if k != "extra"} for t in MORNING}
    intake(site_run, monkeypatch, MORNING[:2] + ["The list is sorted by time."], [fe], change="sort the list by time")
    assert site_run.goal["item_checks"] == {t: {"type": "file-exists", "target": "index.html", "expect": True} for t in MORNING[:2]}
    # the no-errors gate is code's own render check, whatever Identity sent for it
    intake(site_run, monkeypatch, MORNING[:2] + ["The page has no JavaScript errors."], [fe] * 3)
    assert site_run.goal["item_checks"][j2.GATE_TEXT] == {"type": "render-check"}


def test_p30_intake_prompt_asks_one_item_per_required_behaviour(j2, make_run, monkeypatch):
    run = make_run()
    seen = recording(run, monkeypatch, lambda fn: fn == "identity")
    say(run, BREW_LAB)
    fmt, task = next((f, t) for _, f, t in seen if '"item_checks"' in f)
    assert j2.BEHAVIOUR_RULE in task and '"real-run"' in fmt


def test_p30_code_made_items_carry_code_checks(j2):
    g = j2.stage_goal("hld", {"product_name": "Morning"}, {})
    secs = j2.output_def("hld")["sections"]
    assert len(g["done_when"]) == len(secs)
    assert [g["item_checks"][t] for t in g["done_when"]] == [{"type": "section-not-empty", "target": s, "expect": 1} for s in secs]


def test_p30_a_charter_with_an_item_without_an_allowed_check_is_refused(site_run, monkeypatch):
    intake(site_run, monkeypatch, MORNING, [{"type": "file-exists", "target": "index.html"}, {"type": "made-up-check"}, None])
    assert set(site_run.goal["item_checks"]) == {MORNING[0]}
    ok, why = site_run._stamp_check()
    assert not ok and why.startswith("done-when item(s) [2, 3] have no runnable check"), why
    assert any("Charter rejected: done-when item(s) [2, 3]" in m["text"] for m in site_run.chat)


def test_p30_a_builder_sees_its_items_with_check_and_status(j2, make_run, monkeypatch):
    run = make_run()
    seen = recording(run, monkeypatch, lambda fn: fn.startswith("W-"))
    say(run, BREW_LAB)
    built = [(f, t) for _, f, t in seen if "YOUR WORKFLOW: " in t]
    assert built and all('"item_status"' in f for f, _ in built)
    brief = json.loads(built[0][1].split("YOUR WORKFLOW: ", 1)[1].split("\n", 1)[0])
    assert brief["items"] and all(set(x) == {"item", "text", "check", "status"} for x in brief["items"])
    assert all(x["check"] == run.goal["item_checks"][x["text"]] and x["status"] == "not_built" for x in brief["items"])
    assert all(w["item_status"] and {s["status"] for s in w["item_status"].values()} == {"built"}
               for w in run.workflows if w["status"] == "done" and w.get("covers_text"))


PREPARED_NOT_PERFORMED = ("an item whose action you prepared but did not perform (e.g. a message written but never sent, "
                          "for lack of access or credentials) is blocked with that reason, never built")


def test_p30_a_prepared_but_not_performed_action_is_blocked_not_built(make_run, site_run, monkeypatch):
    """Beta fix (c), plumbing only: every builder prompt carries the rule, and a scripted builder reply that follows it ends
    blocked with its reason. Whether a live model follows the rule is not tested here."""
    run = make_run()
    seen = recording(run, monkeypatch, lambda fn: fn.startswith("W-"))
    say(run, BREW_LAB)
    built = [f for _, f, t in seen if "YOUR WORKFLOW: " in t]
    assert built and all(PREPARED_NOT_PERFORMED in f for f in built)
    morning_goal(site_run)
    w = {"id": "W-2", "status": "done", "covers_text": [MORNING[1]]}
    site_run.workflows = [w]
    site_run._store_item_status(w, {"item_status": [{"item": 2, "status": "blocked",
                                                     "reason": "the team channel's webhook address (the post is written, never sent)"}]})
    assert w["item_status"] == {MORNING[1]: {"status": "blocked", "reason": "the team channel's webhook address (the post is written, never sent)"}}
    assert site_run._blocked_items() == [MORNING[1]]


def morning_goal(run, checks=True):
    run.goal = {"statement": "A morning file list", "done_when": list(MORNING), "charter_items": list(MORNING),
                **({"item_checks": {t: {"type": "file-exists", "target": "index.html", "expect": True} for t in MORNING}} if checks else {})}


def test_p30_builder_status_is_a_field_missing_or_unknown_is_not_built(site_run):
    run = site_run
    morning_goal(run)
    w = {"id": "W-1", "covers_text": list(MORNING)}
    run._store_item_status(w, {"human_output": "The channel part is not yet built.", "item_status": [
        {"item": 1, "status": "built", "reason": ""}, {"item": 2, "status": "done"}, {"item": 9, "status": "built"}]})
    assert w["item_status"] == {MORNING[0]: {"status": "built", "reason": ""},       # words in human_output are never read
                                MORNING[1]: {"status": "not_built", "reason": "the builder set no status"},
                                MORNING[2]: {"status": "not_built", "reason": "the builder set no status"}}
    run._store_item_status(w, {"item_status": [{"item": 1, "status": "blocked", "reason": " "},
                                               {"item": 2, "status": "blocked", "reason": "no channel token given"},
                                               {"item": 3, "status": "not_built", "reason": "out of time"}]})
    assert w["item_status"] == {MORNING[0]: {"status": "not_built", "reason": "blocked without a reason"},
                                MORNING[1]: {"status": "blocked", "reason": "no channel token given"},
                                MORNING[2]: {"status": "not_built", "reason": "out of time"}}
    morning_goal(run, checks=False)
    w2 = {"id": "W-2", "covers_text": list(MORNING)}
    run._store_item_status(w2, {})
    assert "item_status" not in w2


def passing_rows(crit):
    return [{"id": f"F-{i}", "item": i, "criterion": c, "verdict": "PASS", "pass": True, "note": "Audit saw it"} for i, c in enumerate(crit, 1)]


def test_p30_audit_pass_without_a_passing_check_is_blocked_by_evidence(site_run):
    run = site_run
    morning_goal(run)
    del run.goal["item_checks"][MORNING[1]]
    run.goal["item_checks"][MORNING[0]] = {"type": "file-exists", "target": "menu.html", "expect": True}
    os.makedirs(Path(run.dir) / "site", exist_ok=True)
    (Path(run.dir) / "site" / "index.html").write_text("<html><body></body></html>")
    rows = passing_rows(MORNING)
    run._item_check_gate(rows, "<html><body></body></html>", {})
    assert [r["verdict"] for r in rows] == ["BLOCKED_BY_EVIDENCE", "BLOCKED_BY_EVIDENCE", "PASS"]
    assert [r["pass"] for r in rows] == [False, False, True]
    assert rows[0]["note"] == "Code ran this item's check (file-exists): menu.html not found in the build. (Audit's own note: Audit saw it)"
    assert rows[1]["note"].startswith("Code ran this item's check (none): this item has no runnable check.")
    assert [e["type"] for e in run.events if e["agent"] == "validator"].count("item_check") == 2


def finish(run, statuses):
    """Two done workflows own the items; the last audit passes everything; then Identity's done."""
    run.workflows = [{"id": "W-1", "name": "List", "status": "done", "covers_text": MORNING[:1] + MORNING[2:], "cycle": 1},
                     {"id": "W-2", "name": "Post", "status": "done", "covers_text": MORNING[1:2], "cycle": 1}]
    for w in run.workflows:
        if statuses is not None:
            run._store_item_status(w, {"item_status": [{"item": run._no(t), **statuses.get(t, {"status": "built", "reason": ""})}
                                                       for t in w["covers_text"]]})
    run.audits = [audit_v0(MORNING, [], output="prd", version=1)]
    run.outcome = None
    run._goal_done({})
    return run.outcome


def test_p30_done_only_when_every_item_is_built_and_passes(make_run):
    run = make_run()
    run.post("user", "A PRD for a morning file list")
    run._apply_output("prd")
    morning_goal(run)
    out = finish(run, {MORNING[1]: {"status": "blocked", "reason": "a channel token"}})
    assert out.startswith("Done with open items: not every done-when item is built."), out
    assert f"done-when item 2: {MORNING[1].rstrip('.')} blocked: needs a channel token. Send it as a follow-up to finish." in out
    run.sites = ["## Users"]
    assert f"{MORNING[1].rstrip('.')} blocked: needs a channel token. Send it as a follow-up to finish." in run._ship_outcome("on request")
    assert finish(run, {}).startswith("Done:") and run._ship_outcome("on request").startswith("Done:")
    # the no-errors gate is code's own check: no workflow owns it, and it is not an open item for that
    run.goal["item_checks"][MORNING[2]] = {"type": "render-check"}
    run.workflows[0]["covers_text"] = MORNING[:1]
    run._store_item_status(run.workflows[0], {"item_status": [{"item": 1, "status": "built", "reason": ""}]})
    assert run._open_items() == []


def test_p30_a_charter_without_item_checks_behaves_as_before(make_run):
    run = make_run()
    run.post("user", "A PRD for a morning file list")
    run._apply_output("prd")
    morning_goal(run, checks=False)
    assert run._stamp_check() == (True, "passes code checks")
    rows = passing_rows(MORNING)
    run._item_check_gate(rows, "", {})
    assert [r["verdict"] for r in rows] == ["PASS"] * 3
    assert run._open_items() == [] and finish(run, None).startswith("Done:")


def test_p30_inside_folder_is_no_item_check_and_the_mock_folder_default_is_file_exists(j2ft, sort_run):
    # review R1-5: inside-folder holds for every build, so it is never evidence for one item
    run = sort_run[0]()
    assert "inside-folder" in run.out["check_types"] and "inside-folder" not in run._item_check_types()
    crit = list(SORT_DONE_WHEN)
    got = run._item_checks_from([{"type": "inside-folder", "target": "."}, {"type": "file-exists", "target": "sort_files.py"},
                                 {"type": "real-run"}], crit)
    assert set(got) == set(crit[1:])
    assert j2ft.mock_item_check(run.out) == {"type": "file-exists", "target": "main.py", "expect": True}
    assert "main.py" in j2ft.mock_form_folder_files(FT, {})      # the file the mock folder builder always writes


def test_p30_a_served_section_carries_the_earlier_runs_status_or_not_built(site_run, tmp_path):
    # review R1-6: code copies the status the earlier run's builder set; it never sets one
    run = site_run
    morning_goal(run)
    old = tmp_path / "earlier-run"
    old.mkdir()
    (old / "workflows.json").write_text(json.dumps([
        {"id": "W-1", "status": "done", "item_status": {MORNING[0]: {"status": "built", "reason": ""},
                                                        MORNING[1]: {"status": "blocked", "reason": "no channel token given"}}},
        {"id": "W-2", "status": "failed", "item_status": {MORNING[1]: {"status": "built", "reason": ""}}}]))
    w = {"id": "W-1", "covers_text": list(MORNING)}
    assert run._served_status(w, {"dir": str(old), "workflow": "W-1"}) == [
        {"item": 1, "status": "built", "reason": ""}, {"item": 2, "status": "blocked", "reason": "no channel token given"},
        {"item": 3, "status": "not_built", "reason": "the earlier run stored no status for it"}]
    assert {x["status"] for x in run._served_status(w, {"dir": str(tmp_path / "gone"), "workflow": "W-1"})} == {"not_built"}


# ---- P31 (D434): a failed dry run goes back to the build; only Run or Don't run answers the real-run question ----------
# Made-up script: it names the folder it was given (a temp copy in the dry run) and fails with "missing argument".
P31_FAIL = "import sys\nsys.stderr.write('cannot read ' + sys.argv[1] + '\\nmissing argument\\n')\nsys.exit(2)\n"
P31_OK = "import os, sys\nopen(os.path.join(sys.argv[1], 'done.txt'), 'w').write('1')\n"
P31_SRT = ("import json, subprocess, sys\na = sys.argv[1:]\njson.load(open(a[a.index('-s') + 1]))\n"
           "sys.exit(subprocess.run(a[a.index('-c') + 1], shell=True).returncode)\n")


@pytest.fixture
def p31(sort_run, tmp_path, monkeypatch):
    """A sort run with W-1 (the script and its real run on item 3) registered and done, its sort_files.py written; the dry
    run goes through a fake srt the test writes."""
    fake = tmp_path / "fake_srt.py"
    fake.write_text(P31_SRT)
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", f"python3 {fake}")
    make, real = sort_run

    def go(script=P31_FAIL):
        run = make()
        reg, refused, _ = run._register(sort_proposals(real, fix=True))
        assert [w["id"] for w in reg] == ["W-1"] and not refused, refused
        run.workflows[0]["status"] = "done"
        (Path(run._out_dir()) / "sort_files.py").write_text(script)
        run.post("user", "Build it and run it on my folder")
        return run
    return go, real


def p31_receipts(run):
    p = Path(run.dir) / "receipts.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if '"real_run"' in x] if p.exists() else []


def p31_revise(run, real, wid):
    """Adaptation's fix: a workflow that revises wid and keeps its real run; built (no failed check), so P28 sees a pass."""
    reg, refused, _ = run._register([{**sort_proposals(real, fix=True)[0], "revises": wid}])
    assert len(reg) == 1 and not refused, refused
    reg[0]["status"] = "done"
    assert run._repeat_build_stop(reg[0]["id"]) is False
    return reg[0]


def test_p31_a_failed_dry_run_goes_to_adaptation_never_to_the_requester(p31):
    go, real = p31
    run = go()
    assert run._ask_real_run({}) is True
    w = run.workflows[0]
    assert not [m for m in run.chat if m.get("real_run")] and run.paused is None and run.turn == "adaptation"
    assert w["status"] == "failed" and w["failure"] == ["dry_run", "exit 2: missing argument"], w.get("failure")
    assert "W-1" not in run.real_runs_asked and run.handoff["kind"] == "propose" and "missing argument" in run.handoff["why"]
    assert not any(m.get("to_user") for m in run.chat if m["who"] == "system")
    # owner (review R1-7): one plain info line, never a warning, a question or a card
    said = [m for m in run.chat if "dry run" in m["text"].lower()]
    assert [m["text"] for m in said] == ["Dry run failed, sent back to the builder"], said
    assert not said[0].get("warning") and not said[0].get("to_user") and not said[0].get("real_run") and run.paused is None
    assert any(e["type"] == "real_run" and "the dry run on copies failed" in str(e) for e in run.events)
    # the plan's open point: P22 takes a replacement real-run workflow for the item whose first real run failed its dry run
    w2 = p31_revise(run, real, "W-1")
    assert w2["real_run"]["checks"] == [3]


def test_p31_two_identical_dry_run_failures_stop_the_cycle_across_temp_folders(p31, j2ft):
    go, real = p31
    run = go()
    run._ask_real_run({})
    w2 = p31_revise(run, real, "W-1")      # its build passed: P28's memory of the dry-run failure stays
    assert run._ask_real_run({}) is True
    sig = [j2ft.build_failure(x) for x in (run.workflows[0], w2)]
    assert sig[0] == sig[1] == ("dry_run", "exit 2: missing argument")
    assert run.turn == "identity" and run.handoff["kind"] == "limit" and run.repeat_steps == ["W-1", w2["id"]]
    assert "the same failure came back twice" in run.handoff["reason"].lower()


def test_p31_the_revising_builder_sees_the_dry_run_output(p31, monkeypatch):
    go, real = p31
    run = go()
    run._ask_real_run({})
    w2 = p31_revise(run, real, "W-1")
    w2["status"] = "registered"
    seen = {}
    monkeypatch.setattr(run, "_file_wf", lambda w: True)      # the brief goes to the builder call, caught here
    monkeypatch.setattr(run, "_run_artifact", lambda w, brief, n: seen.update(brief))
    run._build_workflow({"wid": w2["id"]})
    assert "missing argument" in seen["dry_run_failure"] and seen["dry_run_failure"] == run.workflows[0]["dry_run_output"]
    seen.clear()
    run._build_workflow({"wid": "W-1"})      # a workflow that revises nothing: no field, so other prompts don't change
    assert "dry_run_failure" not in seen and seen


def test_p31_the_receipt_keeps_the_dry_run_output(p31):
    go, _ = p31
    run = go()
    run._ask_real_run({})
    r = p31_receipts(run)[-1]
    assert not r["approved"] and not r["ran"] and r["evidence"] == "not asked: the dry run on copies failed (exit 2: missing argument)"
    assert "missing argument" in r["dry_run"]["output"] and "cannot read <copy>/f0" in r["dry_run"]["output"]
    assert ".dryrun-" not in json.dumps(r["dry_run"]["output"]) and r["dry_run"]["exit"] == 2


def test_p31_the_snapshot_carries_the_code_for_a_real_run_pause(p31):
    go, _ = p31
    run = go(P31_OK)
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run"
    assert run.snapshot()["paused"]["code"] == run.real_runs_asked["W-1"]
    ask = next(m["text"] for m in run.chat if m.get("real_run") == "W-1")
    assert "Or press Run. To decline, press Don't run." in ask and "Any other reply" not in ask


def p31_answer(run, text, auto=False):
    run.post("user", text, **({"auto": True} if auto else {}))
    p, run.paused = run.paused, None      # as _run does when the Requester answers
    run._identity_real_run({**p["handoff"], "answer": text})


def test_p31_a_reply_that_is_not_the_code_asks_again_and_keeps_the_run_open(p31):
    go, real = p31
    run = go(P31_OK)
    run._ask_real_run({})
    code = run.real_runs_asked["W-1"]
    for text, auto in (("yes", False), ("RUN", False), (f"RUN {code}", True)):      # Decide for me's exact code is no answer either
        p31_answer(run, text, auto)
        last = run.chat[-1]
        assert last["who"] == "identity" and f"Not run. Press Run or type RUN {code}." in last["text"], last["text"]
        assert run.paused["kind"] == "real_run" and run.real_runs_asked["W-1"] == code and run.snapshot()["paused"]["code"] == code
        assert str(run.outcome).startswith("Paused") and p31_receipts(run) == [] and not os.path.exists(os.path.join(real, "done.txt"))
    p31_answer(run, f"RUN {code}")
    r = p31_receipts(run)[-1]
    assert r["approved"] and r["ran"] and r["exit"] == 0 and os.path.exists(os.path.join(real, "done.txt"))
    assert run._real_run_pending() == []


def test_p31_dont_run_declines_as_before(p31):
    go, _ = p31
    run = go(P31_OK)
    crit = run.goal["done_when"]
    run.audits = [{"output": FT, "rubric": [], "conditions": [], "after_real_run": [crit[2]],
                   "results": [{"id": f"F-{i}", "item": i, "criterion": c, "pass": i != 3, "verdict": "PASS" if i != 3 else "FAIL",
                                "note": ""} for i, c in enumerate(crit, 1)]}]
    run._ask_real_run({})
    p31_answer(run, "  don't RUN ")
    r = p31_receipts(run)[-1]
    assert not r["approved"] and not r["ran"] and r["evidence"] == "not run: the Requester chose Don't run"
    assert run.paused is None and str(run.outcome).startswith("Done with open items"), run.outcome


def test_p31_decide_for_me_still_never_answers_a_real_run(p31):
    go, _ = p31
    run = go(P31_OK)
    run.auto = True
    run._ask_real_run({})
    assert run.paused["kind"] == "real_run" and run._auto_pick() is None and run.snapshot()["paused"]["auto_waits"]


def test_p31_a_replacements_approved_run_decides_the_item_the_failed_one_checked(p31):
    go, real = p31
    run = go()
    run._ask_real_run({})
    w2 = p31_revise(run, real, "W-1")
    (Path(run._out_dir()) / "sort_files.py").write_text(P31_OK)
    assert run._real_run_pending() and run._ask_real_run({}) and run.paused["kind"] == "real_run"
    p31_answer(run, f"RUN {run.real_runs_asked[w2['id']]}")
    assert run.real_runs_done == {w2["id"]: True} and run._real_run_pending() == []


# ---- P32 (D435): the dry run always runs inside the sandbox runtime (no network), or it is not run --------------------
# Made-up stand-in for srt: it keeps the settings it was given beside itself, then runs the command (no sandbox: test only).
P32_SRT = ("import shutil, subprocess, sys\na = sys.argv[1:]\nshutil.copy(a[a.index('-s') + 1], sys.argv[0] + '.json')\n"
           "sys.exit(subprocess.run(a[a.index('-c') + 1], shell=True).returncode)\n")
NO_DRY_RUN = "No dry run: this computer has no sandbox, so it wasn't tested first"


@pytest.fixture
def p32(p31, tmp_path, monkeypatch):
    """p31's run with the sandbox switch off and the recording stand-in as J2_SANDBOX_CMD; (go, real, settings file)."""
    go, real = p31
    fake = tmp_path / "rec_srt.py"
    fake.write_text(P32_SRT)
    monkeypatch.setenv("J2_SANDBOX", "0")
    monkeypatch.setenv("J2_SANDBOX_CMD", f"python3 {fake}")
    return go, real, tmp_path / "rec_srt.py.json"


def p32_card(run):
    return next(m["text"] for m in run.chat if m.get("real_run") == "W-1")


def test_p32_the_dry_run_is_fenced_with_the_sandbox_switch_off(p32):
    go, _, seen = p32
    run = go(P31_OK)
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run"
    assert json.loads(seen.read_text())["network"]["allowedDomains"] == []
    assert run.real_runs_dry["W-1"]["ran"] is True and run.real_runs_dry["W-1"]["fenced"] is True
    card = p32_card(run)
    assert "dry run on a copy: exit 0" in card and "\nThe dry run had no network access: results may differ." in card, card
    assert NO_DRY_RUN not in card


@pytest.mark.parametrize("env", [{"J2_SANDBOX_CMD": "no-such-sandbox-xyz"},      # the program is not on PATH (Windows, no srt)
                                 {"J2_SANDBOX": None}])      # an offline run without J2_SANDBOX: no sandbox, even with a runtime
def test_p32_without_a_sandbox_runtime_the_dry_run_is_not_run_and_the_card_says_so(p32, monkeypatch, env):
    go, real, seen = p32
    for k, v in env.items():
        monkeypatch.delenv(k) if v is None else monkeypatch.setenv(k, v)
    run = go(P31_OK)

    import subprocess
    real_run = subprocess.run

    def boom(argv, *a, **k):
        if argv[1:2] == ["-c"] and "find_spec" in argv[2]:      # P42 (D447): the import lookup before the dry run, which
            return real_run(argv, *a, **k)                       # imports and runs nothing of the build
        raise AssertionError("the dry run must never run without the sandbox runtime")
    monkeypatch.setattr(subprocess, "run", boom)
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run" and "W-1" in run.real_runs_asked
    dry = run.real_runs_dry["W-1"]
    assert dry["ran"] is False and dry["fenced"] is False and not seen.exists()
    assert dry["evidence"] == "no sandbox runtime here: the dry run was not run, because it never runs with network"
    card = p32_card(run)
    assert f"\n{NO_DRY_RUN}\n" in card and "no network access" not in card and "What it would do" not in card, card
    assert not os.path.exists(os.path.join(real, "done.txt"))


def test_p32_the_approved_run_still_follows_the_switch(p32):
    go, real, seen = p32
    run = go(P31_OK)
    run._ask_real_run({})
    assert seen.exists()
    seen.unlink()
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    r = p31_receipts(run)[-1]
    assert r["approved"] and r["ran"] and r["exit"] == 0 and "without a sandbox" in r["evidence"], r["evidence"]
    assert not seen.exists() and os.path.exists(os.path.join(real, "done.txt"))


# ---- P33 (D436): Audit reads an approved real run's output against the brief; exit 0 alone never passes an item -------------
# Made-up script: it exits 0 and prints what it did (in the dry run, to the temp copy).
P33_OK = ("import os, sys\nprint('moved a.pdf to pdf/')\nprint('moved b.jpg to jpg/')\nprint('sorted 2 files in ' + sys.argv[1])\n"
          "open(os.path.join(sys.argv[1], 'done.txt'), 'w').write('1')\n")      # P35 (D438): what its real run's expect says
P33_SAYS = "the output lists only a.pdf and b.jpg moved; c.txt and d.csv are not named"


@pytest.fixture
def p33(p31, monkeypatch):
    """p31's run with P33_OK written, item 3 pending its real run in the last audit, and every AI call recorded:
    (run, real, calls [(fn, task)])."""
    go, real = p31
    run = go(P33_OK)
    crit = run.goal["done_when"]
    run.audits = [{"output": FT, "rubric": [], "conditions": [], "after_real_run": [crit[2]], "cycle": 1, "version": 1,
                   "all_pass": False,      # as an audit row holds them: the Audit call's context reads these
                   "results": [{"id": f"F-{i}", "item": i, "criterion": c, "pass": i != 3, "verdict": "PASS" if i != 3 else "FAIL",
                                "note": ""} for i, c in enumerate(crit, 1)]}]
    calls, real_call = [], run.call
    monkeypatch.setattr(run, "call", lambda fn, fmt, task, *a, **k: calls.append((fn, task)) or real_call(fn, fmt, task, *a, **k))
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run"
    calls.clear()
    return run, real, calls


def p33_row(run):
    return next(x for x in run.audits[-1]["results"] if x["item"] == 3)


def test_p33_an_approved_run_is_judged_by_audit_on_its_output(p33):
    run, _, calls = p33
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    assert [fn for fn, _ in calls] == ["audit"], calls
    task = calls[0][1]
    assert f"REQUESTER'S BRIEF: {run.request}" in task and "moved b.jpg to jpg/" in task and "sorted 2 files in " in task
    assert '"item": 3' in task and "COMMAND: python3 sort_files.py" in task and "WHAT THE DRY RUN DID TO THE COPY" in task
    row, r = p33_row(run), p31_receipts(run)[-1]
    assert row["pass"] is True and row["verdict"] == "PASS" and row["note"].endswith("Audit read its output: mock: the output was read")
    assert r["approved"] and r["exit"] == 0 and r["audit"] == {"3": {"verdict": "PASS", "evidence": "mock: the output was read"}}
    assert run.real_runs_done == {"W-1": True}
    assert run._run_item_check(run.goal["done_when"][2], {"type": "real-run"}, "", {})["pass"] is True


@pytest.mark.parametrize("finding, says", [({"item": 3, "verdict": "NEEDS_REVISION", "evidence": P33_SAYS}, P33_SAYS),
                                           ({"item": 3, "verdict": "PASS", "evidence": "  "}, "Audit gave no evidence"),
                                           (None, "Audit filed no finding")])
def test_p33_exit_0_with_audit_needs_revision_leaves_the_item_open(p33, monkeypatch, finding, says):
    run, real, calls = p33
    monkeypatch.setattr(run, "call", lambda fn, *a, **k: calls.append((fn, a[1])) or {"say": "x", "findings": [finding] if finding else []})
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    assert [fn for fn, _ in calls] == ["audit"]
    row, r = p33_row(run), p31_receipts(run)[-1]
    assert r["approved"] and r["ran"] and r["exit"] == 0      # it ran and exited 0 ...
    assert row["pass"] is False and row["verdict"] == "NEEDS_REVISION"      # ... and that alone does not pass the item
    assert f"real run receipt (W-1): {r['evidence']}" in row["note"] and row["note"].endswith(f"Audit read its output: {says}")
    assert r["audit"] == {"3": {"verdict": "NEEDS_REVISION", "evidence": says}}
    # the receipt's result stays "approved and exit 0" (review R1-4); Audit's verdict is kept per item, and the check reads both
    assert run.real_runs_done == {"W-1": True} and run.real_run_item_ok == {run.goal["done_when"][2]: False}
    assert run._run_item_check(run.goal["done_when"][2], {"type": "real-run"}, "", {}) == {
        "pass": False, "evidence": "its real run did not pass (approved, exit 0 and Audit PASS)"}
    assert str(run.outcome).startswith("Done with open items"), run.outcome


@pytest.mark.parametrize("answer, ran", [("RUN", {"ran": True, "exit": 3, "output": "boom", "evidence": "sort_files.py exited 3"}),
                                         ("Don't run", None)])
def test_p33_no_judge_call_when_the_run_did_not_pass(p33, j2ft, monkeypatch, answer, ran):
    run, _, calls = p33
    if ran:
        monkeypatch.setattr(j2ft, "real_run", lambda *a, **k: dict(ran))
        answer = f"RUN {run.real_runs_asked['W-1']}"
    p31_answer(run, answer)
    r = p31_receipts(run)[-1]
    assert calls == [] and "audit" not in r and p33_row(run)["verdict"] == "FAIL" and run.real_runs_done == {"W-1": False}
    assert "Audit read" not in p33_row(run)["note"] and str(run.outcome).startswith("Done with open items")


def test_p33_mixed_verdicts_leave_the_passed_item_passing(p33, monkeypatch):
    # review R1-4: PASS on item 3 and NEEDS_REVISION on item 2 of the same run; item 3's check still passes
    run, _, calls = p33
    crit = run.goal["done_when"]
    run.workflows[0]["real_run"]["checks"] = [2, 3]
    monkeypatch.setattr(run, "call", lambda fn, *a, **k: calls.append((fn, a[1])) or {"say": "x", "findings": [
        {"item": 3, "verdict": "PASS", "evidence": "pdf/a.pdf is listed"}, {"item": 2, "verdict": "NEEDS_REVISION", "evidence": "no test ran"}]})
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    rows = {x["item"]: x for x in run.audits[-1]["results"]}
    assert (rows[3]["pass"], rows[3]["verdict"]) == (True, "PASS") and (rows[2]["pass"], rows[2]["verdict"]) == (False, "NEEDS_REVISION")
    assert run.real_runs_done == {"W-1": True} and run.real_run_item_ok == {crit[1]: False, crit[2]: True}
    assert run._run_item_check(crit[2], {"type": "real-run"}, "", {}) == {
        "pass": True, "evidence": "its real run was approved, exited 0 and Audit passed its output"}
    assert run._run_item_check(crit[1], {"type": "real-run"}, "", {})["pass"] is False


def test_p33_an_item_checks_charter_with_a_real_run_item_ends_done(p33):
    # review R1-1: no builder owns an item a real run decides; an approved run, exit 0 and Audit PASS ends "Done:"
    run, _, calls = p33
    crit = run.goal["done_when"]
    run.goal["item_checks"] = {crit[0]: {"type": "file-exists", "target": "sort_files.py", "expect": True},
                               crit[1]: {"type": "file-exists", "target": "sort_files.py", "expect": True},
                               crit[2]: {"type": "real-run"}}
    run.workflows[0]["item_status"] = {crit[0]: {"status": "built", "reason": ""}}
    run.workflows.append({"id": "W-2", "status": "done", "covers_text": [crit[1]],
                          "item_status": {crit[1]: {"status": "built", "reason": ""}}})
    for x in run.audits[-1]["results"]:
        x["pass"], x["verdict"] = (x["item"] != 3, "PASS" if x["item"] != 3 else "FAIL")
    assert run._open_items() == []      # item 3 is the real run's, never "not built: no workflow built it"
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    assert run.real_runs_done == {"W-1": True} and str(run.outcome).startswith("Done:"), run.outcome


def test_p33_without_the_real_run_the_item_stays_open(p33):
    run, real, calls = p33
    crit = run.goal["done_when"]
    assert run._real_run_pending() == [f"done-when item 3: {crit[2]} (its real run has not run)"]
    assert run._run_item_check(crit[2], {"type": "real-run"}, "", {})["pass"] is False
    assert calls == [] and p31_receipts(run) == [] and p33_row(run)["pass"] is False and run.paused["kind"] == "real_run"


def test_p33_the_judge_call_counts_in_budget_and_dollar_mode_and_raises_no_route_event(p33, j2ft, monkeypatch):
    run, _, calls = p33
    monkeypatch.setattr(j2ft, "USD_BUDGET", 20.0)      # dollar mode (P26) for this run's accounting
    n, usd, rows, events = run.calls, run.usd_used, len(run.call_log), len(run.events)
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    assert [fn for fn, _ in calls] == ["audit"] and run.calls == n + 1 and len(run.call_log) == rows + 1
    logged = json.loads((Path(run.dir) / "calls.jsonl").read_text().splitlines()[-1])
    assert logged["fn"] == "audit" and logged["usd_counted"] > 0 and run.usd_used == pytest.approx(usd + logged["usd_counted"], abs=1e-6)      # the row rounds to 6 places
    assert not [e for e in run.events[events:] if e["type"] in ("redirect", "invalid_move")]


# ---- beta fix, P30 amended (D433): a blocked item does not hold back the real run ----------------------------------------
def blocked_run(p31, status):
    """p31's run with an item_checks charter: item 1 built (W-1, which also holds the real run of item 3), item 2 with the
    given builder status (W-2) and failed by Audit, item 3 pending its real run."""
    go, _ = p31
    run = go(P33_OK)
    crit = run.goal["done_when"]
    run.goal["item_checks"] = {crit[0]: {"type": "file-exists", "target": "sort_files.py", "expect": True},
                               crit[1]: {"type": "file-exists", "target": "test_sort_files.py", "expect": True},
                               crit[2]: {"type": "real-run"}}
    run.workflows[0]["item_status"] = {crit[0]: {"status": "built", "reason": ""}}
    run.workflows.append({"id": "W-2", "status": "done", "covers_text": [crit[1]], "item_status": {crit[1]: status}})
    run.audits = [{"output": FT, "rubric": [], "conditions": [], "after_real_run": [crit[2]], "cycle": 1, "version": 1,
                   "all_pass": False,
                   "results": [{"id": f"F-{i}", "item": i, "criterion": c, "pass": i == 1,
                                "verdict": "PASS" if i == 1 else "NEEDS_REVISION", "note": "x"} for i, c in enumerate(crit, 1)]}]
    return run


def test_p30_a_blocked_item_does_not_hold_back_the_real_run_and_the_run_ends_done_with_open_items(p31, monkeypatch):
    run = blocked_run(p31, {"status": "blocked", "reason": "a channel token"})
    crit, calls, real_call = run.goal["done_when"], [], run.call
    monkeypatch.setattr(run, "call", lambda fn, *a, **k: calls.append(fn) or real_call(fn, *a, **k))
    run._identity_audit({})
    assert calls == [] and run.paused["kind"] == "real_run" and "W-1" in run.real_runs_asked      # asked at once, by code
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    r = p31_receipts(run)[-1]
    assert r["approved"] and r["ran"] and r["exit"] == 0 and calls == ["audit"]      # only P33's reading of the output
    assert len(run.audits) == 1 and run.paused is None and run.turn is None      # no audit loop, no question: the end
    out = str(run.outcome)
    assert out.startswith("Done with open items: not every done-when item is built."), out
    assert f"done-when item 2: {crit[1].rstrip('.')} blocked: needs a channel token. Send it as a follow-up to finish." in out \
        and "done-when item 3" not in out, out
    assert out.count("done-when item 2") == 1, out      # review R3-2: listed once, with its reason


def test_p30_a_real_run_item_a_builder_set_blocked_is_still_decided_by_its_real_run(p31):
    """Review R3-1: a fix workflow of F-3 owns real-run item 3 and its builder sets it blocked. The Requester declines the
    real run: the run ends "Done with open items" naming the real run, never "Done:"."""
    go, _ = p31
    run = go(P33_OK)
    crit = run.goal["done_when"]
    run.goal["item_checks"] = {crit[0]: {"type": "file-exists", "target": "sort_files.py", "expect": True},
                               crit[1]: {"type": "file-exists", "target": "test_sort_files.py", "expect": True},
                               crit[2]: {"type": "real-run"}}
    run.workflows[0]["item_status"] = {crit[0]: {"status": "built", "reason": ""}, crit[1]: {"status": "built", "reason": ""}}
    run.workflows.append({"id": "W-9", "status": "done", "covers_text": [], "fixes": ["F-3"],
                          "item_status": {crit[2]: {"status": "blocked", "reason": "needs the real folder"}}})
    run.audits = [{"output": FT, "rubric": [], "conditions": [], "after_real_run": [crit[2]], "cycle": 1, "version": 1,
                   "all_pass": False,
                   "results": [{"id": f"F-{i}", "item": i, "criterion": c, "pass": i < 3,
                                "verdict": "PASS" if i < 3 else "NEEDS_REVISION", "note": "x"} for i, c in enumerate(crit, 1)]}]
    assert crit[2] in run._owned_items(run.workflows[-1])
    run._identity_audit({})
    p31_answer(run, "Don't run")
    out = str(run.outcome)
    assert run.real_runs_done == {"W-1": False} and out.startswith("Done with open items: the real run did not pass."), out
    assert out.count("done-when item 3") == 1, out
    assert run._blocked_items() == []      # a builder's status never decides a real-run item


def to_be_confirmed(run, n, fact):
    """Identity's charter field to_be_confirmed names item n, and the latest audit marks it TO_BE_CONFIRMED (as
    _audit_findings does for that entry), whatever the builder set."""
    crit = run.goal["done_when"]
    run.goal["to_be_confirmed"] = [{"criterion": crit[n - 1], "fact": fact}]
    row = next(r for r in run.audits[-1]["results"] if r["item"] == n)
    row.update(verdict="TO_BE_CONFIRMED", note=f"Waiting on the Requester: {fact}. (Audit's own note: x)", **{"pass": False})


def test_p30_a_to_be_confirmed_item_is_blocked_with_its_missing_fact(p31):
    """Beta fix (b): a charter with one to_be_confirmed item: it is blocked, its reason the entry's fact (a field, never a
    word of a note), so it does not hold back the real run, and the outcome names it once with that fact."""
    run = blocked_run(p31, {"status": "built", "reason": "the post is written, it was never sent"})      # 8b10: built
    crit = run.goal["done_when"]
    to_be_confirmed(run, 2, "the team channel's address")
    assert run._blocked_items() == [crit[1]]
    assert run._open_items() == [f"done-when item 2: {crit[1].rstrip('.')} blocked: needs the team channel's address. "
                                 "Send it as a follow-up to finish."]
    run._identity_audit({})
    assert run.paused["kind"] == "real_run" and "W-1" in run.real_runs_asked      # it does not hold back the real run
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    out = str(run.outcome)
    assert out.startswith("Done with open items: not every done-when item is built."), out
    assert f"done-when item 2: {crit[1].rstrip('.')} blocked: needs the team channel's address. Send it as a follow-up to finish." \
        in out and out.count("done-when item 2") == 1, out
    run.sites = ["x"]
    assert run._ship_outcome("on request").count("done-when item 2") == 1      # listed once there too


def test_p30_a_to_be_confirmed_real_run_item_is_never_blocked(p31):
    run = blocked_run(p31, {"status": "built", "reason": ""})
    to_be_confirmed(run, 3, "the real folder")      # review R3-1: only its receipt and Audit decide a real-run item
    assert run.goal["done_when"][2] not in run._blocked_items()


# ---- beta fix d, P30 amended (D433): a blocked item with no real run ends the run at once -------------------------------
FOLLOW_UP = "Send it as a follow-up to finish."
WEBHOOK = "the team channel's webhook address"


def no_real_run(sort_run, status, tbc=False):
    """A folder run (no render check, as 8b10) with no planned real run: item 1 built by W-1 and passed, item 2 owned by W-2
    with the given builder status and failed by Audit (TO_BE_CONFIRMED when tbc: the charter names it)."""
    make, _ = sort_run
    run = make()
    crit = run.goal["done_when"] = list(SORT_DONE_WHEN[:2])
    run.goal["item_checks"] = {t: {"type": "file-exists", "target": "sort_files.py", "expect": True} for t in crit}
    run.workflows = [{"id": "W-1", "status": "done", "covers_text": [crit[0]], "item_status": {crit[0]: {"status": "built", "reason": ""}}},
                     {"id": "W-2", "status": "done", "covers_text": [crit[1]], "item_status": {crit[1]: status}}]
    run.sites = ["x"]
    run.audits = [{"output": FT, "rubric": [], "conditions": [], "cycle": 1, "version": 1, "all_pass": False,
                   "results": [{"id": f"F-{i}", "item": i, "criterion": c, "pass": i == 1,
                                "verdict": "PASS" if i == 1 else "NEEDS_REVISION", "note": "x"} for i, c in enumerate(crit, 1)]}]
    if tbc:
        to_be_confirmed(run, 2, WEBHOOK)
    return run


def calls_of(run, monkeypatch):
    calls, real_call = [], run.call
    monkeypatch.setattr(run, "call", lambda fn, *a, **k: calls.append(fn) or real_call(fn, *a, **k))
    return calls


@pytest.mark.parametrize("status, tbc", [({"status": "blocked", "reason": WEBHOOK}, False),      # the builder's field (c)
                                         ({"status": "blocked", "reason": f"{WEBHOOK}."}, False),      # R4-3: no ".."
                                         ({"status": "built", "reason": "the post is written"}, True)])      # the charter's (b), 8b10
def test_p30_a_blocked_item_with_no_real_run_ends_the_run_at_once(sort_run, monkeypatch, status, tbc):
    run = no_real_run(sort_run, status, tbc)
    crit, calls = run.goal["done_when"], calls_of(run, monkeypatch)
    run._identity_audit({})
    out = str(run.outcome)
    assert calls == [] and len(run.audits) == 1 and run.turn is None and run.paused is None, (calls, out)      # no Identity,
    assert out.startswith("Done with open items: not every done-when item is built."), out      # no Adaptation, no audit
    assert f"{crit[1].rstrip('.')} blocked: needs {WEBHOOK}. {FOLLOW_UP}" in out and out.count("done-when item 2") == 1, out
    assert "done-when item 1" not in out and ".." not in out, out


@pytest.mark.parametrize("status", [{"status": "not_built", "reason": "out of time"},
                                    {"status": "built", "reason": ""}])      # Audit failed it while its builder says built
def test_p30_a_not_built_or_failed_item_still_goes_back_to_adaptation(sort_run, monkeypatch, status):
    run = no_real_run(sort_run, status)
    calls = calls_of(run, monkeypatch)
    run._identity_audit({})
    assert run.outcome is None and calls == ["identity"] and run.turn == "adaptation", (calls, run.outcome)


@pytest.mark.parametrize("status", [{"status": "not_built", "reason": "out of time"},
                                    {"status": "built", "reason": ""}])
def test_p30_a_blocked_item_beside_an_open_one_does_not_end_the_run(sort_run, monkeypatch, status):
    """Only when every other item is built and passes: a blocked item 2 beside a not-built or failed item 1 goes back."""
    run = no_real_run(sort_run, {"status": "blocked", "reason": WEBHOOK})
    crit = run.goal["done_when"]
    run.workflows[0]["item_status"] = {crit[0]: status}
    if status["status"] == "built":
        run.audits[-1]["results"][0].update(verdict="NEEDS_REVISION", **{"pass": False})
    calls = calls_of(run, monkeypatch)
    run._identity_audit({})
    assert run.outcome is None and calls == ["identity"] and run.turn == "adaptation", (calls, run.outcome)


@pytest.mark.parametrize("status", [{"status": "not_built", "reason": "the builder set no status"},
                                    {"status": "built", "reason": ""}])      # Audit failed it: built alone never passes
def test_p30_an_item_that_is_not_blocked_still_holds_back_the_real_run(p31, status):
    run = blocked_run(p31, status)
    run._identity_audit({})
    assert "W-1" not in run.real_runs_asked and not [m for m in run.chat if m.get("real_run")] and p31_receipts(run) == []


# ---- beta fix, P30 amended (D433): a follow-up to a run with a to-be-confirmed item goes through Identity's intake ---------
TEAM_POST = "Post the summary to the team channel."      # made up, as the fact (WEBHOOK)


def scripted_identity(run, *, tbc, dropped=()):
    """The mock Identity, scripted by structure, never by a message's words: the first charter adds TEAM_POST and (tbc)
    records WEBHOOK as to be confirmed for it; an intake given the current charter (a follow-up) returns that charter
    without any to_be_confirmed entry, as Identity does when the follow-up supplies the fact. Every charter leaves out the
    brief items in dropped (review R5-2). Returns those intakes' tasks."""
    intakes, real_call = [], run.call

    def call(fn, fmt, task, mock, *a, **k):
        if fn != "identity":
            return real_call(fn, fmt, task, mock, *a, **k)

        def scripted():
            r = json.loads(mock())
            goal = r.get("goal")
            if isinstance(goal, dict) and dropped:
                goal["dropped_from_brief"] = list(dropped)
            if isinstance(goal, dict) and (not run.goal or "CURRENT CHARTER" not in task):      # run 1's charter (again
                if TEAM_POST not in goal["done_when"]:                                       # after a drop answer)
                    goal["done_when"] = list(goal["done_when"]) + [TEAM_POST]
                goal["to_be_confirmed"] = [{"item": goal["done_when"].index(TEAM_POST) + 1, "fact": WEBHOOK}] if tbc else []
            elif isinstance(goal, dict) and "CURRENT CHARTER" in task:
                intakes.append(task)
                goal["to_be_confirmed"] = []
            return json.dumps(r)
        return real_call(fn, fmt, task, scripted, *a, **k)
    run.call = call
    return intakes


def first_run(make_run, tbc):
    """A mock Brew Lab run. With tbc, a website's open fact holds a necessary condition, so Identity asks the limit question
    (`only_tbc`) and the Requester picks "finish as it is" (a folder run, 8b10, ends at once, fix d)."""
    run = make_run()
    scripted_identity(run, tbc=tbc)
    say(run, BREW_LAB)
    if tbc:
        assert run.paused and "finish as it is" in run.outcome, run.outcome
        say(run, "Finish as it is")
    return run


def follow_up(make_run, earlier, text, tbc):
    run = make_run()
    run.rehydrate(earlier.dir)
    intakes = scripted_identity(run, tbc=tbc)
    say(run, text)
    return run, intakes


def test_p30_a_follow_up_that_gives_the_missing_fact_finishes_the_item(make_run):
    run = first_run(make_run, tbc=True)
    n = run.goal["done_when"].index(TEAM_POST) + 1
    assert run.outcome.startswith("Done with open items"), run.outcome
    assert f"done-when item {n}: {TEAM_POST.rstrip('.')} blocked: needs {WEBHOOK}. {FOLLOW_UP}" in run.outcome, run.outcome
    follow, intakes = follow_up(make_run, run, "The webhook address is https://hooks.example.test/T000/B000", tbc=True)
    assert len(intakes) == 1 and WEBHOOK in intakes[0] and "leave its entry out of to_be_confirmed" in intakes[0], \
        "Identity's intake gets the charter with the entry, and is told it may drop it"
    assert follow.goal["to_be_confirmed"] == [] and TEAM_POST in follow.goal["done_when"]
    assert follow._item_states()[TEAM_POST]["status"] == "built" and len(follow.audits) > len(run.audits)
    row = next(r for r in follow.audits[-1]["results"] if r["criterion"] == TEAM_POST)
    assert row["pass"] is True, row
    assert follow.outcome.startswith("Done:") and "open items" not in follow.outcome and FOLLOW_UP not in follow.outcome, \
        follow.outcome


def test_p30_a_folder_run_ended_by_fix_d_takes_the_fact_from_a_follow_up(sort_run, monkeypatch):
    """review R5-4, the 8b10 shape: a folder output whose to-be-confirmed item is the only gap ends at once (fix d) with its
    "blocked: needs" line; the follow-up giving the fact goes first to Identity's intake with the current charter, which clears
    the entry. The rebuild is not asserted: the mock Adaptation's workflows are refused for a folder type."""
    run = no_real_run(sort_run, {"status": "built", "reason": "the post is written"}, tbc=True)
    crit = run.goal["done_when"]
    run._identity_audit({})
    assert f"{crit[1].rstrip('.')} blocked: needs {WEBHOOK}. {FOLLOW_UP}" in str(run.outcome), run.outcome
    assert run.goal["to_be_confirmed"], run.goal
    run.done, run.status = True, "waiting"      # the run ended (fix d); the Requester sends the follow-up
    calls = calls_of(run, monkeypatch)
    intakes = scripted_identity(run, tbc=True)
    say(run, "The webhook address is https://hooks.example.test/T000/B000")
    assert calls and calls[0] == "identity" and len(intakes) == 1, calls
    assert "CURRENT CHARTER" in intakes[0] and WEBHOOK in intakes[0] and "leave its entry out of to_be_confirmed" in intakes[0]
    assert run.goal["to_be_confirmed"] == [], run.goal["to_be_confirmed"]


@pytest.mark.parametrize("reply", [None, []])      # None: Identity's charter has no to_be_confirmed key at all
def test_p30_a_follow_up_keeps_a_to_be_confirmed_entry_unless_identity_lists_the_key(sort_run, monkeypatch, reply):
    """review R5-5: a follow-up that does not give the fact goes through Identity's intake; a charter reply without the
    to_be_confirmed key keeps the old entry (its item is still in the charter); an explicit empty list clears it."""
    run = no_real_run(sort_run, {"status": "built", "reason": "the post is written"}, tbc=True)
    run._identity_audit({})
    run.done, run.status, old, real_call, seen = True, "waiting", list(run.goal["to_be_confirmed"]), run.call, []

    def call(fn, fmt, task, mock, *a, **k):
        if fn != "identity" or "CURRENT CHARTER" not in task:
            return real_call(fn, fmt, task, mock, *a, **k)

        def scripted():
            r = json.loads(mock())
            r["goal"]["done_when"] = list(run.goal["done_when"])      # everything already in it is kept, as the prompt asks
            r["goal"].pop("to_be_confirmed", None) if reply is None else r["goal"].update(to_be_confirmed=reply)
            return json.dumps(r)
        out = real_call(fn, fmt, task, scripted, *a, **k)
        seen.append(True)
        return out
    run.call = call
    say(run, "Add a line about visiting hours to the notes")
    assert seen, "Identity's intake ran"
    assert run.goal["to_be_confirmed"] == (old if reply is None else []), run.goal["to_be_confirmed"]


def test_p30_a_follow_up_does_not_ask_again_about_brief_items_already_dropped(make_run):
    """review R5-2: run 1's charter left a brief item out and the Requester answered "Drop them"; the follow-up that gives
    the fact goes through Identity's intake, whose charter still leaves it out, and must not ask the drop question again."""
    run = make_run()
    scripted_identity(run, tbc=True, dropped=["a printed menu"])
    say(run, BREW_LAB)
    assert run.paused and run.paused["kind"] == "charter_drop", run.paused
    say(run, "Drop them")
    if run.paused:
        say(run, "Finish as it is")
    assert run.goal["dropped_from_brief"] == ["a printed menu"] and run.outcome.startswith("Done with open items"), run.outcome
    follow = make_run()
    follow.rehydrate(run.dir)
    intakes = scripted_identity(follow, tbc=True, dropped=["a printed menu"])
    say(follow, "The webhook address is https://hooks.example.test/T000/B000")
    assert len(intakes) == 1 and not (follow.paused and follow.paused["kind"] == "charter_drop"), follow.paused
    assert follow.goal["to_be_confirmed"] == [] and follow.outcome.startswith("Done:"), follow.outcome


def test_p30_a_follow_up_still_asks_about_a_brief_item_newly_dropped(make_run):
    """review R5-2, guard: a brief item the follow-up's charter newly leaves out is still asked about."""
    run = make_run()
    scripted_identity(run, tbc=True)
    say(run, BREW_LAB)
    say(run, "Finish as it is")
    follow = make_run()
    follow.rehydrate(run.dir)
    scripted_identity(follow, tbc=True, dropped=["a printed menu"])
    say(follow, "The webhook address is https://hooks.example.test/T000/B000")
    assert follow.paused and follow.paused["kind"] == "charter_drop", follow.paused


def test_p30_a_follow_up_without_a_to_be_confirmed_item_skips_identitys_intake(make_run):
    run = first_run(make_run, tbc=False)
    assert run.outcome.startswith("Done:"), run.outcome
    follow, intakes = follow_up(make_run, run, "Add a section for visiting hours", tbc=False)
    assert intakes == [] and follow.outcome.startswith("Done:"), follow.outcome


# ---- review R4-1, P30 amended (D433): a stage left with a blocked item is named in the run's outcome -------------------------
CAMPUS_DOCS = ("Design docs for Campus Notes. Users: students and teachers. Problem: students lose track of their notes. "
               "Must-have features: upload notes, search notes. Constraints: free to use. Success: 50 uploads per week.")


NEW_RUN = "Start a new run with it to finish."      # review R5-3: the hint of an earlier stage's blocked item


def blocked_prd(make_run, text=CAMPUS_DOCS, stages=("prd",)):
    """A mock design-document chain whose builders in the given stages set the stage's first item blocked (a reason ending
    in ".", R4-3); the other stages are clean. Returns the finished run and the PRD's blocked line up to "blocked" (with
    more stages, {stage: that line})."""
    run = make_run()
    run.budget, real_call, targets = 400, run.call, {}

    def call(fn, fmt, task, mock, *a, **k):
        def scripted():
            text = mock()      # a section builder's reply: its JSON, then the section's markdown
            r, end = json.JSONDecoder().raw_decode(text) if run.stage_kind in stages and fn.startswith("W-") else (None, 0)
            if not isinstance(r, dict) or not r.get("item_status"):
                return text
            target = targets.setdefault(run.stage_kind, r["item_status"][0]["item"])
            for s in r["item_status"]:
                if s["item"] == target:
                    s.update(status="blocked", reason=f"{WEBHOOK}.")
            return json.dumps(r) + text[end:]
        return real_call(fn, fmt, task, scripted, *a, **k)
    run.call = call
    say(run, text)
    assert set(targets) == set(stages), (run.stages, targets)
    goals = {a["stage"]: a["goal"] for a in run.stage_archive}
    items = {k: f"done-when item {n}: {goals[k]['done_when'][n - 1].rstrip('.')}" for k, n in targets.items()}
    return run, (f"PRD {items['prd']}" if stages == ("prd",) else items)


def test_p30_a_blocked_item_in_an_earlier_stage_is_named_when_the_chain_ends(make_run):
    """Fix d ends the PRD stage at once and the chain moves on, so the run must end "Done with open items" naming it."""
    run, item = blocked_prd(make_run)
    assert run.stages == ["prd", "hld", "lld"], run.stages
    out = str(run.outcome)
    assert out.startswith("Done with open items"), out
    assert f"{item} blocked: needs {WEBHOOK}. {NEW_RUN}" in out and FOLLOW_UP not in out, out      # R5-3
    assert out.count(f"needs {WEBHOOK}") == 1 and ".." not in out, out      # R4-3


def test_p30_only_an_earlier_stages_blocked_item_says_start_a_new_run(make_run):
    """review R5-3: a follow-up continues the last stage only, so an earlier stage's blocked item says start a new run, and
    the last stage's keeps "Send it as a follow-up to finish."."""
    run, items = blocked_prd(make_run, stages=("prd", "lld"))
    out = str(run.outcome)
    assert out.startswith("Done with open items"), out
    assert f"PRD {items['prd']} blocked: needs {WEBHOOK}. {NEW_RUN}" in out, out
    assert f"{items['lld']} blocked: needs {WEBHOOK}. {FOLLOW_UP}" in out, out
    assert out.count(NEW_RUN) == 1 and out.count(FOLLOW_UP) == 1 and ".." not in out, out


def assert_names_blocked(out, item):
    assert out.startswith("Done with open items") and not out.startswith("Done:"), out
    assert f"{item} blocked: needs {WEBHOOK}. {NEW_RUN}" in out and out.count(f"needs {WEBHOOK}") == 1 and ".." not in out, out


def test_p30_a_chain_that_ends_in_a_send_names_an_earlier_stages_blocked_item(make_run, monkeypatch):
    """review R5-1: the chain's last stage is a send deed, so _deeds_finished writes the outcome."""
    monkeypatch.setenv("J2_TEST_EMAIL", "me@example.invalid")
    monkeypatch.delenv("J2_SEND_MODE", raising=False)
    run, item = blocked_prd(make_run, CAMPUS_DOCS + " When the documents are finished, send a test email to me with a "
                                                    "short summary of the PRD.")
    assert run.stages == ["prd", "hld", "lld", "send_email"] and run.deed_log, run.stages
    assert_names_blocked(str(run.outcome), item)
    assert run.deed_log[0]["note"] in run.outcome, run.outcome      # what the send did is still said


@pytest.mark.parametrize("ending", ["_stages_finished", "_run_tpl_stage_end"])
def test_p30_every_chain_ending_names_an_earlier_stages_blocked_item(make_run, ending):
    """review R5-1: the stage gate's "leave out" (_stages_finished) and a run template's partial stage end write the outcome
    themselves; at the end of the same chain each must still name the PRD's blocked item."""
    run, item = blocked_prd(make_run)
    run.outcome, run.turn = None, None
    if ending == "_run_tpl_stage_end":
        run.run_tpl = {"name": "Campus", "total": 2, "selected": ["x"]}
    getattr(run, ending)()
    assert_names_blocked(str(run.outcome), item)


def test_p30_finishing_as_it_is_at_the_stage_gate_names_an_earlier_stages_blocked_item(make_run):
    """review R6-1: the stage gate's "finish as it is" (_stage_decision, ship) writes its own outcome; after a PRD with a
    blocked item it must name it, keeping its own "finished as it is ... Not made: ..." words."""
    run, item = blocked_prd(make_run)
    run.outcome, run.turn = None, None      # back to the gate after the PRD: the HLD stage not started
    run.stage_archive = [a for a in run.stage_archive if a["stage"] == "prd"]
    run.stage_i = 0
    run.decisions.append({"kind": "stage"})
    run._read_decision = lambda *a, **k: {"decision": "ship"}
    run._stage_decision({"answer": "Finish as it is", "choices": ["continue", "drop", "ship"], "stage_i": 1,
                         "asked": [{"question": "q"}]})
    out = str(run.outcome)
    assert out.startswith("Done with open items: finished as it is on the Requester's decision. Not made: "), out
    # the gate runs before the HLD begins, so the PRD is still the current stage (stage_kind) and keeps the follow-up hint (R5-3)
    assert f"Still not workable: {item} blocked: needs {WEBHOOK}. {FOLLOW_UP}" in out, out
    assert out.count(f"needs {WEBHOOK}") == 1 and ".." not in out, out


# ---- beta fix, P31 amended (D434): a folder the brief names as ~/x is the same folder as its expanded form ------------------
@pytest.mark.parametrize("stated", ["~/demo/rename-test", "{home}/demo/rename-test"])
def test_p31_a_tilde_folder_and_its_expanded_form_both_register(sort_run, tmp_path, monkeypatch, stated):
    monkeypatch.setenv("HOME", str(tmp_path))      # a made-up home: no real home path in any file
    (tmp_path / "demo" / "rename-test").mkdir(parents=True)
    make, _ = sort_run
    run = make()
    run.request = "Build sort_files.py with a test, then run it on ~/demo/rename-test"
    folder = stated.format(home=tmp_path)
    rr = {**sort_proposals(folder, fix=True)[0]["real_run"], "command": ["python3", "sort_files.py", folder], "folder": folder}
    reg, refused, _ = run._register([{**sort_proposals(folder, fix=True)[0], "real_run": rr}])
    full = str(tmp_path / "demo" / "rename-test")
    assert [w["id"] for w in reg] == ["W-1"] and not refused, refused
    assert reg[0]["real_run"]["folder"] == full and reg[0]["real_run"]["command"] == ["python3", "sort_files.py", full]


def test_p31_a_folder_the_brief_does_not_name_is_still_refused(sort_run, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "demo" / "other").mkdir(parents=True)
    make, _ = sort_run
    run = make()
    run.request = "Build sort_files.py with a test, then run it on ~/demo/rename-test"
    for folder in ("~/demo/other", str(tmp_path / "demo" / "other")):
        rr = {**sort_proposals(folder, fix=True)[0]["real_run"], "command": ["python3", "sort_files.py", folder], "folder": folder}
        reg, refused, _ = run._register([{**sort_proposals(folder, fix=True)[0], "real_run": rr}])
        assert reg == [] and len(refused) == 1 and "is not named in the brief" in str(refused[0]), refused


# ---- P34 (D437): a build's output holds only what was built; the CLI's .claude folder is removed and never copied ---------------

CLI_FOLDER = {".claude/.cc-writes/.keep": "", ".claude/note.json": "{}"}      # made up: the CLI's staging folder, and a file beside it


def test_p34_the_cli_folder_is_removed_after_a_builder_call_and_is_not_a_written_file(j2, make_run):
    run = make_run()
    run.post("user", "go")
    tools_call(j2, run, inside=CLI_FOLDER)
    out = Path(run.dir) / "out"
    assert (out / "build.py").is_file() and not (out / ".claude").exists()
    assert [f["path"] for f in run.call_log[-1]["tools"]["files_written"]] == ["build.py"]
    assert not [e for e in run.events if e["type"] == "outside_write"]


def test_p34_the_outside_write_check_still_stops_a_call_and_the_cli_folder_is_still_removed(j2, make_run):
    run = make_run()
    run.post("user", "go")
    with pytest.raises(j2.BuilderToolFault) as e:
        tools_call(j2, run, extra={"notes.txt": "x"}, inside=CLI_FOLDER)
    assert e.value.files == ["notes.txt"] and not (Path(run.dir) / "out" / ".claude").exists()


def test_p34_no_site_copy_carries_a_claude_folder(j2, make_run):
    run = make_run()
    run.post("user", "go")
    run._apply_output("website")
    out = Path(run._out_dir())
    for rel, body in {run._main_file(): "<!doctype html><title>t</title>", "pages/about.html": "<p>a</p>", **CLI_FOLDER,
                      "pages/.claude/y.json": "{}"}.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(body)
    run._publish_out("<!doctype html><title>t</title>")
    site = Path(run.dir) / "site"
    assert (site / run._main_file()).is_file() and (site / "pages" / "about.html").is_file()
    assert not [p for p in site.rglob(".claude")]


# ---- P35 (D438): a real run states what it creates, changes and deletes; the dry run must match and leave read-only copies alone
# SUT-12 (impact.md §9), made up: in/ holds two notes, out/ is empty, and copy.py <input> <output> upper-cases each input file
# into the output and writes report.txt. Passed the folders swapped, it reads the empty out/ and writes report.txt into in/.
P35_COPY = ("import os, sys\nsrc, dst = sys.argv[1], sys.argv[2]\nnames = sorted(os.listdir(src))\n"
            "for n in names:\n    open(os.path.join(dst, n), 'w').write(open(os.path.join(src, n)).read().upper())\n"
            "open(os.path.join(dst, 'report.txt'), 'w').write(str(len(names)) + ' files\\n')\nprint('processed', len(names))\n")
P35_ALL = {"created": ["a.txt", "b.txt", "report.txt"], "changed": [], "deleted": []}
P35_DONE_WHEN = ["copy.py upper-cases each file of a given input folder into a given output folder.",
                 "copy.py writes report.txt with the number of files it copied.",
                 "Run on the notes folder, out/ holds A.txt-style upper-case copies and report.txt."]


@pytest.fixture
def p35(j2ft, tmp_path, monkeypatch):
    """(go, in, out): go(args, expect) makes a run whose W-1 (copy.py, its real run writing out/ and reading in/, checking
    item 3) is registered and done. The dry run goes through P31's fake srt, which enforces nothing, so a swap is caught
    only by code's own checks."""
    fake = tmp_path / "fake_srt.py"
    fake.write_text(P31_SRT)
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", f"python3 {fake}")
    src, dst = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    dst.mkdir()
    (src / "a.txt").write_text("alpha\n")
    (src / "b.txt").write_text("beta\n")
    counter = itertools.count(1)

    def go(args=("in", "out"), expect=P35_ALL):
        run = j2ft.J2Run(run_dir=tmp_path / "runs" / f"j2-20261124-0900{next(counter):02d}-5e12")
        run._apply_output(FT)
        run.request = f"Build copy.py, then run it on my notes in {src} and write the results to {dst}"
        run.goal, run.budget = {"statement": "x", "done_when": list(P35_DONE_WHEN)}, 100
        os.makedirs(run._out_dir(), exist_ok=True)
        where = {"in": str(src), "out": str(dst)}
        rr = {"command": ["python3", "copy.py", *(where[a] for a in args)], "folder": str(dst), "reads": [str(src)],
              "why": "The brief asks to run it on the Requester's notes.", "checks": [3], "expect": expect}
        reg, refused, _ = run._register([{**sort_proposals(str(dst), fix=True)[0], "real_run": rr}])
        assert [w["id"] for w in reg] == ["W-1"] and not refused, refused
        run.workflows[0]["status"] = "done"
        (Path(run._out_dir()) / "copy.py").write_text(P35_COPY)
        run.post("user", "Build it and run it on my notes")
        return run
    return go, src, dst


def p35_again(run):
    """Adaptation's fix: a workflow that revises W-1 with the same real run; its build passed (P28 sees a pass)."""
    rr = {k: v for k, v in run.workflows[0]["real_run"].items()}
    reg, refused, _ = run._register([{**sort_proposals(rr["folder"], fix=True)[0], "real_run": rr, "revises": "W-1"}])
    assert len(reg) == 1 and not refused, refused
    reg[0]["status"] = "done"
    assert run._repeat_build_stop(reg[0]["id"]) is False
    return reg[0]


def test_p35_swapped_folders_reproduce_and_now_go_back_to_the_build(p35):
    """The reported bug: before P35 the swapped command's dry run said "0 created" and the Requester was asked to run it."""
    go, src, dst = p35
    run = go(("out", "in"), {"created": ["*.txt"], "changed": [], "deleted": []})
    assert run._ask_real_run({}) is True
    w = run.workflows[0]
    assert not [m for m in run.chat if m.get("real_run")], "the swapped command reached the Requester"
    assert w["status"] == "failed" and w["failure"] == [
        "dry_run", "wrote into a folder it may only read: read folder 1: 1 created, 0 deleted, 0 changed"], w["failure"]
    assert "W-1" not in run.real_runs_asked and run.paused is None and run.turn == "adaptation"
    assert run.handoff["kind"] == "propose" and "wrote into a folder it may only read" in run.handoff["why"]
    r = p31_receipts(run)[-1]
    assert not r["approved"] and not r["ran"] and r["dry_run"]["reads_changed"] == {
        "1": {"created": ["report.txt"], "deleted": [], "changed": []}}, r["dry_run"]
    assert sorted(os.listdir(src)) == ["a.txt", "b.txt"] and os.listdir(dst) == [], "the real folders are untouched"


def test_p35_expect_mismatch_missing_and_unexpected(j2ft):
    em = j2ft.expect_mismatch
    dry = {"created": ["z.txt", "a.txt", "report.txt"], "changed": [], "deleted": [], "output": "/tmp/.dryrun-x/f0"}
    assert em(P35_ALL | {"created": ["*.txt"]}, dry) == ""
    assert em(P35_ALL | {"created": ["a.txt", "report.txt", "z.txt"]}, dry) == ""
    assert em(P35_ALL | {"created": ["*.csv", "a.txt"]}, dry) == \
        "created: expected *.csv, got none; created: unexpected report.txt; created: unexpected z.txt"
    assert em({"created": ["*.txt"], "changed": [], "deleted": []}, {**dry, "deleted": ["old.txt"]}) == "deleted: unexpected old.txt"
    assert em({"created": ["*.txt"], "changed": ["keep.txt"], "deleted": []}, dry) == "changed: expected keep.txt, got none"
    assert em(P35_ALL, {"created": [], "changed": [], "deleted": []}) == \
        "created: expected a.txt, got none; created: expected b.txt, got none; created: expected report.txt, got none"
    assert ".dryrun-" not in em(P35_ALL, dry)


def test_p35_a_matching_dry_run_is_asked(p35):
    go, src, dst = p35
    run = go()
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run" and "W-1" in run.real_runs_asked
    card = next(m["text"] for m in run.chat if m.get("real_run") == "W-1")
    assert "Created (3): a.txt, b.txt, report.txt" in card and run.workflows[0]["status"] == "done"
    assert run.real_runs_dry["W-1"]["reads_changed"] == {} and os.listdir(dst) == []


def test_p35_a_file_the_expect_left_out_goes_back(p35):
    go, _, dst = p35
    run = go(expect={"created": ["a.txt", "b.txt"], "changed": [], "deleted": []})
    assert run._ask_real_run({}) is True
    w = run.workflows[0]
    assert not [m for m in run.chat if m.get("real_run")] and run.turn == "adaptation" and "W-1" not in run.real_runs_asked
    assert w["failure"] == ["dry_run", "not what it said it would do: created: unexpected report.txt"], w["failure"]
    assert p31_receipts(run)[-1]["dry_run"]["expect_mismatch"] == "created: unexpected report.txt"
    assert os.listdir(dst) == []


def test_p35_two_identical_mismatches_stop_the_cycle(p35, j2ft):
    go, _, _ = p35
    run = go(expect={"created": ["a.txt", "b.txt"], "changed": [], "deleted": []})
    run._ask_real_run({})
    w2 = p35_again(run)
    assert run._ask_real_run({}) is True
    sig = [j2ft.build_failure(x) for x in (run.workflows[0], w2)]
    assert sig[0] == sig[1] == ("dry_run", "not what it said it would do: created: unexpected report.txt")
    assert run.turn == "identity" and run.handoff["kind"] == "limit" and run.repeat_steps == ["W-1", w2["id"]]


@pytest.mark.parametrize("expect", [None, {"created": [], "changed": [], "deleted": []}, "report.txt",
                                    {"created": ["report.txt"]}, {"created": ["report.txt", ""], "changed": [], "deleted": []},
                                    {"created": ["/abs/report.txt"], "changed": [], "deleted": []},
                                    {"created": ["../report.txt"], "changed": [], "deleted": []},
                                    {"created": ["./report.txt"], "changed": [], "deleted": []},      # review R1-8: never matches a
                                    {"created": ["pdf/"], "changed": [], "deleted": []}])      # dry-run file path, so refused
def test_p35_a_real_run_without_expect_is_refused_with_its_own_key(p35, j2ft, expect):
    go, src, dst = p35
    run = go()
    rr = {**run.workflows[0]["real_run"], "expect": expect}
    if expect is None:
        rr.pop("expect")
    run.workflows[0]["status"] = "failed"      # as after a failed dry run: the fix proposes the same real run again
    reg, refused, _ = run._register([{**sort_proposals(str(dst), fix=True)[0], "real_run": rr, "revises": "W-1"}])
    assert not reg and len(refused) == 1 and "real_run expect" in refused[0], refused
    assert run.rejections[-1]["key"] == ["real_run_expect"]
    assert j2ft.real_run_expect_problems(rr) and j2ft.real_run_expect_problems({**rr, "expect": P35_ALL}) == []


def test_p35_the_proposal_rules_ask_for_expect(j2ft, tmp_path, monkeypatch):
    monkeypatch.setenv("J2_AGENT_TOOLS", "1")
    run = j2ft.J2Run(run_dir=tmp_path / "runs" / "j2-20261124-090100-5e12")
    run._apply_output(FT)
    assert run.out.get("test_runner") and j2ft.llm.tools_on()
    # P41 (D446) appends its environment rule right after this one and P44 (D449) its internet rule after that
    assert run.ATOM_RULES.endswith(j2ft.REAL_RUN_EXPECT_RULE + j2ft.REAL_RUN_ENV_RULE + j2ft.REAL_RUN_NET_RULE) and '"expect"' in j2ft.REAL_RUN_EXPECT_RULE
    assert "file paths or globs" in j2ft.REAL_RUN_EXPECT_RULE and "never a folder" in j2ft.REAL_RUN_EXPECT_RULE
    monkeypatch.setenv("J2_AGENT_TOOLS", "0")
    run._apply_output(FT)
    assert j2ft.REAL_RUN_EXPECT_RULE not in run.ATOM_RULES


# ---- P41 (D446): a script gets only PATH, HOME, locale and temp folder, plus what its plan states; secrets go by file path ---
# Made-up script: it reports its environment's names, a few values and the secret file's size, never the file's content;
# printed, and written to argv[2] when given (the dry run's copies are gone once it returns).
P41_DUMP = ("import json, os, sys\nf = os.environ.get('API_CRED_FILE')\nok = bool(f) and os.path.isfile(f)\n"
            "r = json.dumps({'names': sorted(os.environ), 'vals': {k: os.environ.get(k) for k in ('SUT22_LEAK', "
            "'FAKE_SERVICE_TOKEN', 'PLAN_LEVEL', 'API_CRED_FILE', 'J2_SMTP_PASSWORD', 'PYTHONPATH')}, "
            "'cred': {'exists': ok, 'size': os.path.getsize(f) if ok else None}}, separators=(',', ':'))\n"
            "print(r)\nif len(sys.argv) > 2:\n    open(sys.argv[2], 'w').write(r)\n")
# Made-up stand-in for srt: it records its own environment and the allowRead it was given, then runs the -c command as a
# list (never a shell; no sandbox: test only).
P41_SRT = ("import json, os, shlex, subprocess, sys\na = sys.argv[1:]\nconf = json.load(open(a[a.index('-s') + 1]))\n"
           "json.dump({'env': sorted(os.environ), 'allowRead': conf['filesystem']['allowRead']}, open(sys.argv[0] + '.seen', 'w'))\n"
           "sys.exit(subprocess.run(shlex.split(a[a.index('-c') + 1])).returncode)\n")
P41_CRED = "made-up-cred"


@pytest.fixture
def p41(tmp_path, monkeypatch):
    """(out, folder, cred, fake srt, report): a built folder holding the dump, the stated folder, a made-up secret file, the
    fake srt and where the dump writes its report; the app's environment holds made-up leaks."""
    out, folder = tmp_path / "out", tmp_path / "folder"
    out.mkdir()
    folder.mkdir()
    (out / "dump.py").write_text(P41_DUMP)
    cred = tmp_path / "cred.txt"
    cred.write_text(P41_CRED)
    fake = tmp_path / "fake_srt.py"
    fake.write_text(P41_SRT)
    monkeypatch.setenv("SUT22_LEAK", "x")
    monkeypatch.setenv("FAKE_SERVICE_TOKEN", "x")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "made-up-path"))
    monkeypatch.setenv("J2_SANDBOX", "0")
    return out, folder, cred, fake, tmp_path / "report.json"


def p41_rr(folder, report=None, **extra):
    return {"command": [sys.executable, "dump.py", str(folder)] + ([str(report)] if report else []), "folder": str(folder), **extra}


def p41_dump(res):
    assert res["ran"] and res["exit"] == 0, res
    return json.loads(res["output"].strip().splitlines()[-1])


def p41_fake_srt(monkeypatch, fake):
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", shlex.join([sys.executable, str(fake)]))      # shlex.join: split back exactly, on any OS
    return Path(str(fake) + ".seen")


P41_ENV = {"settings": {"PLAN_LEVEL": "basic"}}


def test_p41_real_run_env_is_clean_without_a_sandbox(j2ft, p41):
    out, folder, *_ = p41
    d = p41_dump(j2ft.real_run(str(out), p41_rr(folder), 30))
    assert d["vals"] == dict.fromkeys(d["vals"]), d["vals"]      # no leak, no PYTHONPATH, no SMTP password
    # __CF*: macOS adds __CF_USER_TEXT_ENCODING to every process it starts
    assert {n for n in d["names"] if not n.startswith("__CF")} - set(j2ft.llm.RUN_PASS_NAMES) == set(), d["names"]


def test_p41_real_run_gets_settings_and_secret_paths(j2ft, p41, monkeypatch):
    out, folder, cred, fake, _ = p41
    rr = p41_rr(folder, **P41_ENV, secret_files={"API_CRED_FILE": str(cred)})
    res = j2ft.real_run(str(out), rr, 30)
    d = p41_dump(res)
    assert d["vals"]["PLAN_LEVEL"] == "basic" and d["vals"]["API_CRED_FILE"] == str(cred) and d["vals"]["SUT22_LEAK"] is None
    assert d["cred"] == {"exists": True, "size": len(P41_CRED)} and P41_CRED not in json.dumps(res)
    seen = p41_fake_srt(monkeypatch, fake)
    res = j2ft.real_run(str(out), rr, 30)
    d = p41_dump(res)
    assert "in the sandbox" in res["evidence"], res["evidence"]
    assert d["vals"]["PLAN_LEVEL"] == "basic" and d["vals"]["API_CRED_FILE"] == str(cred) and d["vals"]["SUT22_LEAK"] is None
    assert str(cred) in json.loads(seen.read_text())["allowRead"] and P41_CRED not in json.dumps(res)


def test_p41_dry_run_gets_placeholders_never_real_paths(j2ft, p41, monkeypatch):
    out, folder, cred, fake, report = p41
    seen = p41_fake_srt(monkeypatch, fake)
    monkeypatch.setenv("J2_SANDBOX", "0")      # the dry run is fenced whatever the switch says (P32)
    dry = j2ft.real_run_dry(str(out), p41_rr(folder, report, **P41_ENV, secret_files={"API_CRED_FILE": str(cred)}), 30)
    assert dry["ran"] is True and dry["exit"] == 0, dry
    d = json.loads(report.read_text())
    ph = d["vals"]["API_CRED_FILE"]
    assert d["vals"]["SUT22_LEAK"] is None and d["vals"]["PLAN_LEVEL"] == "basic" and ph != str(cred)
    area = os.path.dirname(ph)
    assert os.path.basename(area) == "secrets" and os.path.basename(os.path.dirname(area)).startswith(".dryrun-")
    assert os.path.dirname(os.path.dirname(area)) == os.path.dirname(os.path.realpath(out)), ph      # outside every copy (f<n>)
    assert d["cred"] == {"exists": True, "size": 0}, "a real, empty placeholder file"
    allow = json.loads(seen.read_text())["allowRead"]
    assert ph in allow and str(cred) not in allow
    assert not os.path.exists(ph), "removed with the dry run's temp folder"
    assert not any("secrets" in p for k in ("created", "changed", "deleted") for p in dry[k]), dry
    assert P41_CRED not in json.dumps(dry)


@pytest.mark.skipif(os.name == "nt", reason="on Windows the names are passed to srt with env=; there is no env program to wrap with")
def test_p41_srt_itself_gets_the_base_only(j2ft, p41, monkeypatch):
    out, folder, cred, fake, _ = p41
    seen = p41_fake_srt(monkeypatch, fake)
    d = p41_dump(j2ft.real_run(str(out), p41_rr(folder, **P41_ENV, secret_files={"API_CRED_FILE": str(cred)}), 30))
    srt_env = json.loads(seen.read_text())["env"]
    assert not {"PLAN_LEVEL", "API_CRED_FILE", "SUT22_LEAK"} & set(srt_env), srt_env
    assert d["vals"]["PLAN_LEVEL"] == "basic" and d["vals"]["API_CRED_FILE"] == str(cred)


def test_p41_smtp_password_from_env_file_never_reaches_a_script(j2ft, p41, monkeypatch, tmp_path):
    from sutra_app.engine import paths
    out, folder, *_ = p41
    monkeypatch.setenv("J2_SMTP_PASSWORD", "")
    (tmp_path / ".env").write_text("J2_SMTP_PASSWORD=made-up-pass\n")
    assert paths.load_env_file(tmp_path / ".env") == ("J2_SMTP_PASSWORD",)
    assert os.environ["J2_SMTP_PASSWORD"] == "made-up-pass"
    d = p41_dump(j2ft.real_run(str(out), p41_rr(folder), 30))
    assert "J2_SMTP_PASSWORD" not in d["names"] and d["vals"]["J2_SMTP_PASSWORD"] is None


@pytest.mark.skipif(shutil.which("srt") is None or not sys.platform.startswith(("darwin", "linux")), reason="needs the sandbox runtime")
def test_p41_real_srt_reads_a_secret_file_under_home(j2ft, p41, monkeypatch, tmp_path):
    out, folder, *_ = p41
    home = tmp_path / "home"
    home.mkdir()
    cred = home / "cred.txt"
    cred.write_text(P41_CRED)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", "srt")
    res = j2ft.real_run(str(out), p41_rr(folder, secret_files={"API_CRED_FILE": str(cred)}), 60)
    assert res["exit"] == 0 and "in the sandbox" in res["evidence"], res
    assert p41_dump(res)["cred"] == {"exists": True, "size": len(P41_CRED)}


# What srt 0.0.81 adds itself for the script it starts (generateProxyEnvVars, sandbox-utils.js): its own localhost proxy, with a
# per-process random token (sandbox-manager.js, randomBytes(16)), and the per-tool proxy and trust settings that point at it.
# None of these comes from the app: srt is started with the base environment only (test_p41_srt_itself_gets_the_base_only).
SRT_OWN_NAMES = {
    "SANDBOX_RUNTIME", "TMPDIR", "PWD", "SHLVL", "_",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY", "GRPC_PROXY", "RSYNC_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "ftp_proxy", "grpc_proxy", "no_proxy",
    "DOCKER_HTTP_PROXY", "DOCKER_HTTPS_PROXY", "GIT_CONFIG_PARAMETERS", "GIT_SSH_COMMAND", "SRT_SSH_PROXY_COMMAND",
    "JAVA_TOOL_OPTIONS", "CLOUDSDK_PROXY_TYPE", "CLOUDSDK_PROXY_ADDRESS", "CLOUDSDK_PROXY_PORT",
    "CLOUDSDK_PROXY_USERNAME", "CLOUDSDK_PROXY_PASSWORD",
}


@pytest.mark.skipif(shutil.which("srt") is None or not sys.platform.startswith(("darwin", "linux")), reason="needs the sandbox runtime")
def test_p41_real_srt_adds_only_its_own_proxy_names(j2ft, p41, monkeypatch, tmp_path):
    """Under the real srt the script sees the base, the plan's settings and srt's own local-proxy names: nothing else."""
    out, folder, *_ = p41
    home = tmp_path / "home"      # srt denies reads under ~; a temp HOME keeps this interpreter readable, as the tests below do
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", "srt")
    res = j2ft.real_run(str(out), p41_rr(folder, **P41_ENV), 60)
    assert res["exit"] == 0 and "in the sandbox" in res["evidence"], res
    d = p41_dump(res)
    extra = {n for n in d["names"] if not n.startswith("__CF")} - set(j2ft.llm.RUN_PASS_NAMES) - set(P41_ENV["settings"])
    assert extra <= SRT_OWN_NAMES, sorted(extra - SRT_OWN_NAMES)
    assert d["vals"]["SUT22_LEAK"] is None and d["vals"]["J2_SMTP_PASSWORD"] is None


@pytest.mark.skipif(shutil.which("srt") is None or not sys.platform.startswith(("darwin", "linux")), reason="needs the sandbox runtime")
def test_p41_real_srt_reads_a_secret_file_named_through_a_symlink(j2ft, p41, monkeypatch, tmp_path):
    """R1-2: the stored path is the real file, so srt's allowRead (and the env and the card) name what the script opens."""
    out, folder, *_ = p41
    keys = tmp_path / "home" / "keys"
    keys.mkdir(parents=True)
    (keys / "real.txt").write_text(P41_CRED)
    link = tmp_path / "home" / "link.txt"
    link.symlink_to(keys / "real.txt")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", "srt")
    stored = j2ft.real_run_env_fields({"secret_files": {"API_CRED_FILE": "~/link.txt"}})      # as _register stores it
    assert stored == {"secret_files": {"API_CRED_FILE": os.path.realpath(keys / "real.txt")}}
    res = j2ft.real_run(str(out), p41_rr(folder, **stored), 60)
    assert res["exit"] == 0 and "in the sandbox" in res["evidence"], res
    assert p41_dump(res)["cred"] == {"exists": True, "size": len(P41_CRED)}


@pytest.mark.skipif(shutil.which("srt") is None or not sys.platform.startswith(("darwin", "linux")), reason="needs the sandbox runtime")
def test_p41_real_srt_dry_run_cannot_read_a_secret_file_outside_home(j2ft, p41, monkeypatch, tmp_path):
    """R1-3: model code that hard-codes a secret file's path outside HOME reads nothing in the dry run; the real run reads it."""
    out, folder, *_ = p41
    (tmp_path / "home").mkdir()
    secret = tmp_path / "elsewhere" / "cred.txt"      # outside HOME, so denyRead ["~"] alone would not cover it
    secret.parent.mkdir()
    secret.write_text(P41_CRED)
    (out / "peek.py").write_text("import sys\ntry:\n    print('READ', open(sys.argv[1]).read())\n"
                                 "except OSError as e:\n    print('DENIED', type(e).__name__)\n")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", "srt")
    rr = {"command": [sys.executable, "peek.py", str(secret)], "folder": str(folder),
          "secret_files": {"API_CRED_FILE": str(secret)}}
    dry = j2ft.real_run_dry(str(out), rr, 60)
    assert dry["ran"] is True and "DENIED" in dry["output"] and P41_CRED not in json.dumps(dry), dry
    res = j2ft.real_run(str(out), rr, 60)
    assert res["exit"] == 0 and "READ " + P41_CRED in res["output"], res


def test_p41_test_rerun_sees_no_app_variable(j2ft, p41):
    """T3 (owner Q4): the builder's test rerun gets the clean base only; a made-up app variable never reaches it."""
    _, folder, *_ = p41
    (folder / "t.py").write_text("import os, sys\nsys.exit(1 if {'SUT22_LEAK', 'PYTHONPATH'} & set(os.environ) else 0)\n")
    res = j2ft.sandbox_rerun(str(folder), [sys.executable, "{target}"], "t.py", 30)
    assert res["pass"] is True, res


# Made-up values for the base names added in the SUT-22 follow-up; the script exits 0 only when it sees every one.
P41_USER_ENV = {"USER": "made-up-user", "LOGNAME": "made-up-user", "SHELL": "/made/up/sh", "TZ": "UTC", "TERM": "dumb"}
P41_READS = "import os, sys\nwant = {}\nsys.exit(0 if all(os.environ.get(k) == v for k, v in want.items()) else 3)\n"


def test_p41_dry_run_passes_a_script_that_reads_user(j2ft, p41, monkeypatch):
    """D446 follow-up: USER, LOGNAME, SHELL, TZ and TERM are in the base, so a script reading $USER passes its dry run."""
    out, folder, _, fake, _ = p41
    for k, v in P41_USER_ENV.items():
        monkeypatch.setenv(k, v)
    (out / "reads.py").write_text(P41_READS.format(P41_USER_ENV))
    p41_fake_srt(monkeypatch, fake)
    dry = j2ft.real_run_dry(str(out), {"command": [sys.executable, "reads.py"], "folder": str(folder)}, 30)
    assert dry["ran"] is True and dry["exit"] == 0, dry
    assert set(P41_USER_ENV) <= set(j2ft.llm.RUN_PASS_NAMES)


def test_p41_an_arbitrary_setting_reaches_the_script(j2ft, p41, monkeypatch, tmp_path):
    """D446: any variable the plan names as a setting reaches the script, in the real run and in the dry run."""
    out, folder, _, fake, _ = p41
    named = {"MY_TOOL_HOME": "/made/up/path"}
    assert j2ft.real_run_env_problems({"settings": named}, "", str(tmp_path)) == []
    (out / "reads.py").write_text(P41_READS.format(named))
    rr = {"command": [sys.executable, "reads.py"], "folder": str(folder), "settings": named}
    res = j2ft.real_run(str(out), rr, 30)
    assert res["ran"] and res["exit"] == 0, res
    assert j2ft.real_run(str(out), {**rr, "settings": {}}, 30)["exit"] == 3, "not named: not passed"
    p41_fake_srt(monkeypatch, fake)
    assert j2ft.real_run(str(out), rr, 30)["exit"] == 0
    dry = j2ft.real_run_dry(str(out), rr, 30)
    assert dry["ran"] is True and dry["exit"] == 0, dry


def test_p41_builders_and_planner_are_told_the_base_and_to_name_the_rest(j2ft, tmp_path, monkeypatch):
    """D446 follow-up: Adaptation's rule and the tools builder's prompt list the base names and say any other variable is
    named in the real run's settings (secrets as secret_files)."""
    base = "PATH, HOME, USER, LOGNAME, SHELL, TZ, TERM"
    assert base in j2ft.REAL_RUN_ENV_RULE and '"settings"' in j2ft.REAL_RUN_ENV_RULE
    rule = j2ft.SCRIPT_ENV_RULE
    assert base in rule and "settings" in rule and "secret_files" in rule
    monkeypatch.setenv("J2_AGENT_TOOLS", "1")
    run = j2ft.J2Run(run_dir=tmp_path / "runs" / "j2-20261125-090200-5e12")
    run._apply_output(FT)
    run.goal, run.budget = {"statement": "copy", "done_when": ["copy.py copies the files"]}, 100
    os.makedirs(run._out_dir(), exist_ok=True)
    w = {"id": "W-1", "name": "copier", "purpose": "copy", "outputs": [f"{FT}/copy.py"], "status": "running", "calls_used": 0,
         "retries_used": 0, "cost": 10, "cycle": 1, "section": "W-1", "covers": [1],
         "atoms": [{"id": "W-1.a1", "goal": "copy", "expected_output": [],
                    "verification": [{"text": "copy.py exists", "type": "file-exists", "target": "copy.py", "expect": True}]}]}
    run.workflows = [w]
    j2ft.add_workflow_agent("W-1")
    prompts = []

    def call(fn, fmt, prompt, mock, **kw):
        prompts.append(prompt)
        (Path(run._out_dir()) / "copy.py").write_text("print('made-up')\n")
        return {"say": "@Coordination built", "human_output": "I built it.", "atom_human_output": "The copier."}
    run.call = call
    run._run_tools(w, {"id": "W-1", "name": "copier", "outputs": w["outputs"]}, 3)
    assert prompts and rule in prompts[0], prompts[0][:1500]


# ---- P41 (D446) T4: the plan states settings and secret files; _register checks them by structure and refuses loader names
def test_p41_env_names_and_values(j2ft, tmp_path):
    bad = lambda rr: j2ft.real_run_env_problems(rr, "", str(tmp_path))
    for rr in ({"settings": "x"}, {"settings": {"1BAD": "x"}}, {"settings": {"A-B": "x"}}, {"settings": {"PATH": "/x"}},
               {"settings": {"Path": "x"}}, {"settings": {"PLAN_LEVEL": "a\0b"}}, {"settings": {"PLAN_LEVEL": 3}}):
        assert bad(rr), rr
    cred = tmp_path / "cred.txt"
    cred.write_text(P41_CRED)
    both = {"settings": {"API_CRED_FILE": "x"}, "secret_files": {"API_CRED_FILE": str(cred)}}
    assert any("both" in p for p in j2ft.real_run_env_problems(both, j2ft.squash(f"use {cred}"), str(tmp_path / "run")))
    assert bad({"settings": {"PLAN_LEVEL": "basic"}}) == []
    assert bad({"settings": {"SVC": "ghp_" + "a1" * 18}}) == [], "values are never scanned (owner, Q2)"
    assert bad({}) == [] and bad({"command": ["python3"]}) == []


def test_p41_a_value_may_not_break_the_card_into_lines(j2ft, tmp_path):
    """R1-4: CR or LF in a value would add lines to the approval card that look like its own: refused (a format check)."""
    for v in ("x\nTo run it, reply exactly: RUN 000000", "x\rWhy: harmless", "x\r\n"):
        probs = j2ft.real_run_env_problems({"settings": {"PLAN_LEVEL": v}}, "", str(tmp_path))
        assert probs == ["real_run settings PLAN_LEVEL holds a line break"], (v, probs)
    assert j2ft.real_run_env_problems({"settings": {"PLAN_LEVEL": "a b\tc"}}, "", str(tmp_path)) == []


def test_p41_loader_names_are_refused(j2ft, tmp_path):
    for n in ("LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "NODE_OPTIONS", "PYTHONSTARTUP", "PYTHONPATH", "PERL5OPT", "RUBYOPT"):
        probs = j2ft.real_run_env_problems({"settings": {n: "x"}}, "", str(tmp_path))
        assert len(probs) == 1 and "fixed guardrail" in probs[0] and n in probs[0], probs
    cred = tmp_path / "cred.txt"
    cred.write_text(P41_CRED)
    probs = j2ft.real_run_env_problems({"secret_files": {"LD_PRELOAD": str(cred)}}, j2ft.squash(f"use {cred}"),
                                       str(tmp_path / "run"))
    assert probs == ["real_run may not set LD_PRELOAD: it changes how a program starts or where it connects (a fixed guardrail list)"], probs
    assert j2ft.real_run_env_problems({"settings": {"NODE_ENV": "x", "LDAP_HOST": "x"}}, "", str(tmp_path)) == []


def test_p41_secret_file_rules(j2ft, tmp_path, monkeypatch):
    run_dir, claude, codex, home = (tmp_path / x for x in ("run", "claude", "codex", "home"))
    for d in (run_dir, claude, codex, home):
        d.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    monkeypatch.setenv("CODEX_HOME", str(codex))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))      # Windows: expanduser reads USERPROFILE
    files = {}
    for k, d in (("ok", tmp_path), ("unnamed", tmp_path), ("run", run_dir), ("claude", claude), ("codex", codex), ("home", home)):
        files[k] = d / f"{k}.txt"
        files[k].write_text(P41_CRED)
    named = [str(files[k]) for k in ("ok", "run", "claude", "codex")] + [str(tmp_path / "gone.txt"), str(tmp_path)]
    source = j2ft.squash("Use " + ", ".join(named) + " and ~/home.txt")
    probs = lambda p: j2ft.real_run_env_problems({"secret_files": {"API_CRED_FILE": p}}, source, str(run_dir))
    for p in ("cred.txt", str(files["unnamed"]), str(tmp_path / "gone.txt"), str(tmp_path), str(files["run"]),
              str(files["claude"]), str(files["codex"])):
        assert probs(p), p
    assert any("not named" in x for x in probs(str(files["unnamed"])))
    assert any("sign-in" in x for x in probs(str(files["claude"])))
    assert probs(str(files["ok"])) == [] and probs("~/home.txt") == []
    assert j2ft.real_run_env_fields({"secret_files": {"API_CRED_FILE": "~/home.txt"}, "command": ["x"]}) == {
        "secret_files": {"API_CRED_FILE": os.path.expanduser("~/home.txt")}}


def test_p41_case_variant_of_a_sign_in_file_is_refused(j2ft, tmp_path, monkeypatch):
    """R1-1: on a case-insensitive disk (macOS, Windows default) an upper-cased path names the same sign-in file: refused."""
    claude = tmp_path / "claudecfg"
    claude.mkdir()
    (claude / "creds.json").write_text(P41_CRED)
    if not (tmp_path / "CLAUDECFG").exists():
        pytest.skip("the temp folder's file system is case-sensitive: a case variant is another file there")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    variant = str(tmp_path / "CLAUDECFG" / "creds.json")
    probs = j2ft.real_run_env_problems({"secret_files": {"API_CRED_FILE": variant}}, j2ft.squash(f"use {variant}"),
                                       str(tmp_path / "run"))
    assert any("sign-in" in x for x in probs), probs


@pytest.fixture
def p41_reg(j2ft, tmp_path, monkeypatch):
    """register(**fields): a fresh p35-style run (copy.py reading in/, writing out/) whose request names the made-up secret
    file and a fake Claude sign-in folder's file; it registers W-1 with fields on its real run: (run, registered, refused)."""
    src, dst, claude, home = (tmp_path / x for x in ("in", "out", "claude", "home"))
    for d in (src, dst, claude, home):
        d.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    (home / "cred.txt").write_text(P41_CRED)
    (claude / "cred.txt").write_text(P41_CRED)
    counter = itertools.count(1)

    def register(**fields):
        run = j2ft.J2Run(run_dir=tmp_path / "runs" / f"j2-20261125-0900{next(counter):02d}-5e12")
        run._apply_output(FT)
        run.request = (f"Build copy.py, then run it on my notes in {src} and write the results to {dst}; "
                       f"the key is in ~/cred.txt (or {claude / 'cred.txt'})")
        run.goal, run.budget = {"statement": "x", "done_when": list(P35_DONE_WHEN)}, 100
        rr = {"command": ["python3", "copy.py", str(src), str(dst)], "folder": str(dst), "reads": [str(src)],
              "why": "The brief asks to run it on the Requester's notes.", "checks": [3], "expect": P35_ALL, **fields}
        reg, refused, _ = run._register([{**sort_proposals(str(dst), fix=True)[0], "real_run": rr}])
        return run, reg, refused
    return register, home, claude


def test_p41_register_stores_and_refuses_with_its_key(p41_reg):
    register, home, claude = p41_reg
    run, reg, refused = register(settings={"PLAN_LEVEL": "basic"}, secret_files={"API_CRED_FILE": "~/cred.txt"})
    assert len(reg) == 1 and not refused, refused
    assert reg[0]["real_run"]["settings"] == {"PLAN_LEVEL": "basic"}
    assert reg[0]["real_run"]["secret_files"] == {"API_CRED_FILE": os.path.expanduser("~/cred.txt")}      # written out
    run, reg, refused = register(secret_files={"API_CRED_FILE": str(claude / "cred.txt")})
    assert not reg and len(refused) == 1 and run.rejections[-1]["key"] == ["real_run_env"], refused
    run, reg, refused = register(settings={"NODE_OPTIONS": "--x"})
    assert not reg and "fixed guardrail" in refused[0] and run.rejections[-1]["key"] == ["real_run_env"], refused
    run, reg, refused = register()
    assert len(reg) == 1 and not {"settings", "secret_files"} & set(reg[0]["real_run"]), reg[0]["real_run"]


def test_p41_rule_joins_atom_rules_with_tools_and_runner(j2ft, tmp_path, monkeypatch):
    monkeypatch.setenv("J2_AGENT_TOOLS", "1")
    run = j2ft.J2Run(run_dir=tmp_path / "runs" / "j2-20261125-090100-5e12")
    run._apply_output(FT)
    assert run.out.get("test_runner") and j2ft.llm.tools_on()
    assert run.ATOM_RULES.endswith(j2ft.REAL_RUN_EXPECT_RULE + j2ft.REAL_RUN_ENV_RULE + j2ft.REAL_RUN_NET_RULE)      # P44 (D449)
    rule = j2ft.REAL_RUN_ENV_RULE
    assert '"settings"' in rule and '"secret_files"' in rule and "placeholder" in rule and "NODE_OPTIONS" in rule
    monkeypatch.setenv("J2_AGENT_TOOLS", "0")
    run._apply_output(FT)
    assert j2ft.REAL_RUN_ENV_RULE not in run.ATOM_RULES


P41_NONE = "\nSettings it gets: none beyond the basics (PATH, HOME, user, shell, time zone, terminal, language, temp folder)"
P41_PLACEHOLDERS = "\nThe dry run got the settings and an empty placeholder file for each secret file."


def test_p41_card_lines(j2ft, tmp_path):
    lines = j2ft.real_run_env_lines
    assert lines({"command": ["x"]}) == P41_NONE
    assert lines({"settings": {}, "secret_files": {}}) == P41_NONE
    assert lines({"settings": {"PLAN_LEVEL": "basic", "REGION": "eu"}}) == "\nSettings it gets: PLAN_LEVEL=basic, REGION=eu"
    cred = tmp_path / "cred.txt"
    cred.write_text(P41_CRED)
    card = lines({"settings": {"PLAN_LEVEL": "basic"}, "secret_files": {"API_CRED_FILE": str(cred)}})
    assert card == ("\nSettings it gets: PLAN_LEVEL=basic"
                    f"\nSecret files it may read (the app never opens them): API_CRED_FILE = {cred}" + P41_PLACEHOLDERS)
    assert P41_CRED not in card
    card = lines({"secret_files": {"API_CRED_FILE": str(cred)}})      # a secret file alone: no setting, still every line
    assert card.startswith(P41_NONE + "\nSecret files it may read") and card.endswith(P41_PLACEHOLDERS)


@pytest.mark.skipif(sys.platform == "win32", reason="the FT form's runner is python3, which a Windows runner may not have")
def test_p41_card_lists_every_setting_before_approval(j2ft, p41_reg, monkeypatch, tmp_path):
    register, home, _ = p41_reg
    fake = tmp_path / "fake_srt.py"
    fake.write_text(P41_SRT)
    p41_fake_srt(monkeypatch, fake)
    cred = os.path.expanduser("~/cred.txt")
    run, reg, refused = register(settings={"PLAN_LEVEL": "basic", "REGION": "eu"}, secret_files={"API_CRED_FILE": "~/cred.txt"})
    assert len(reg) == 1 and not refused, refused
    run.workflows[0]["status"] = "done"
    os.makedirs(run._out_dir(), exist_ok=True)
    (Path(run._out_dir()) / "copy.py").write_text(P35_COPY)
    (tmp_path / "in" / "a.txt").write_text("alpha\n")
    (tmp_path / "in" / "b.txt").write_text("beta\n")
    run.post("user", "Build it and run it on my notes")
    assert run._ask_real_run({}) is True and run.paused["kind"] == "real_run"
    card = next(m["text"] for m in run.chat if m.get("real_run") == "W-1")
    assert "\nSettings it gets: PLAN_LEVEL=basic, REGION=eu\n" in card, card
    assert f"\nSecret files it may read (the app never opens them): API_CRED_FILE = {cred}\n" in card, card
    assert P41_PLACEHOLDERS in card and card.index("Settings it gets") < card.index("To run it, reply exactly")
    assert P41_CRED not in card
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    r = p31_receipts(run)[-1]
    assert r["approved"] and r["ran"] and r["exit"] == 0, r
    assert r["settings"] == {"PLAN_LEVEL": "basic", "REGION": "eu"} and r["secret_files"] == {"API_CRED_FILE": cred}
    assert P41_CRED not in json.dumps(r) and P41_CRED not in json.dumps(run.chat)


# ---- P42 (D447): a build with a requirements.txt gets an environment of its own, installed only after RUN <code>; its test, its dry
# run and its real run use that python. No network: a fake python stands in for the interpreter, its venv module and pip, and a fake
# sandbox runtime records its settings. The fakes hold their log's path: D446's clean environment passes them no variable ---------------------------------------------------------------------------------------------
# TEST ONLY: "-m venv" makes a folder holding a copy of this file, "-m pip install" writes one module per requirements line into it,
# "-m pip list" lists them, and anything else runs with the real python, which sees those modules only through the environment's copy.
P42_FAKE_PYTHON = """#!{exe}
import json, os, shutil, subprocess, sys
me, a = os.path.abspath(sys.argv[0]), sys.argv[1:]
site = os.path.join(os.path.dirname(os.path.dirname(me)), "site")
def note(kind):
    with open({log!r}, "a") as f:
        f.write(json.dumps({{"kind": kind, "argv": a, "python": me}}) + "\\n")
if a[:2] == ["-m", "venv"]:
    note("venv")
    os.makedirs(os.path.join(a[2], "bin"))
    os.makedirs(os.path.join(a[2], "site"))
    shutil.copy(me, os.path.join(a[2], "bin", "python"))
    sys.exit(0)
if a[:3] == ["-m", "pip", "install"]:
    note("pip install")
    if os.path.exists({log!r} + ".pipfail"):
        sys.stderr.write("ERROR: No matching distribution found for " + open({log!r} + ".pipfail").read() + "\\n")
        sys.exit(1)
    for line in open(a[a.index("-r") + 1]):
        name, _, version = line.strip().partition("==")
        if name:
            open(os.path.join(site, name.replace("-", "_") + ".py"), "w").write("VERSION = %r\\n" % version)
    sys.exit(0)
if a[:3] == ["-m", "pip", "list"]:
    print(json.dumps([{{"name": f[:-3], "version": open(os.path.join(site, f)).read().split("'")[1]}}
                      for f in sorted(os.listdir(site)) if f.endswith(".py")]))
    sys.exit(0)
note("run")
env = dict(os.environ)
if os.path.isdir(site):
    env["PYTHONPATH"] = site
sys.exit(subprocess.run([{exe!r}] + a, env=env).returncode)
"""
# TEST ONLY stand-in for the sandbox runtime (srt -s <settings> -c <command>): records the settings, runs the command WITHOUT a sandbox
P42_FAKE_SANDBOX = """import json, os, subprocess, sys
LOG = __LOG__
a = sys.argv[1:]
with open(LOG, "a") as f:
    f.write(json.dumps({"kind": "sandbox", "settings": json.load(open(a[a.index("-s") + 1])), "command": a[a.index("-c") + 1]}) + "\\n")
sys.exit(subprocess.run(a[a.index("-c") + 1], shell=True).returncode)
"""
P42_GOOD = "import sys, os\nopen(os.path.join(sys.argv[1], 'out.txt'), 'w').write('done')\n"
P42_NEEDS = "import sys, os\nimport pulsedep\nopen(os.path.join(sys.argv[1], 'out.txt'), 'w').write(pulsedep.VERSION)\n"
# the fake interpreter is a `#!` script: Windows can't run one, so the tests that install with it run on macOS and Linux only
p42_posix = pytest.mark.skipif(os.name == "nt", reason="the fake interpreter is a #! script, which Windows can't run")
P42_FILES = {"s.py": P42_NEEDS, "test_s.py": "import pulsedep\nassert pulsedep.VERSION == '1.2.0'\n", "requirements.txt": "pulsedep==1.2.0\n"}


@pytest.fixture(scope="module")
def j2env(tmp_path_factory):
    """J2 with the folder type FT, builder tools on (the general path), its data folder and the fake interpreter."""
    base = tmp_path_factory.mktemp("j2-p42")
    fake, srt = base / "python3.12", base / "fake_srt.py"
    fake.write_text(P42_FAKE_PYTHON.format(exe=sys.executable, log=str(base / "fake.log")), encoding="utf-8")
    fake.chmod(0o755)
    srt.write_text(P42_FAKE_SANDBOX.replace("__LOG__", repr(str(base / "fake.log"))), encoding="utf-8")
    with fresh_j2(base, J2_TYPES_DIR=base / "types", J2_AGENT_TOOLS="1", J2_DATA_DIR=base / "data", J2_RUN_PYTHON=fake) as mod:
        mod.j2_types.create(FT, "Script", None, form="agent")
        mod._data_type.cache_clear()
        mod.p42_log = lambda kind: [r for r in map(json.loads, (base / "fake.log").read_text().splitlines())
                                    if r["kind"] == kind] if (base / "fake.log").exists() else []
        mod.p42_srt = f"{sys.executable} {srt}"
        mod.p42_pip_fail = base / "fake.log.pipfail"      # while this file exists the fake pip fails, naming its text
        yield mod


@pytest.fixture
def env_run(j2env, tmp_path):
    """made(files, status, attempts, test) -> (run, workflow): one workflow that plans a real run on a folder of the Requester's."""
    real = tmp_path / "inbox"
    real.mkdir()
    (real / "mail.txt").write_text("one")
    counter = itertools.count(1)

    def made(files, status="done", attempts=1, test=None):
        run = j2env.J2Run(run_dir=tmp_path / "runs" / f"j2-20261124-0628{next(counter):02d}-01a2")
        run._apply_output(FT)
        run.goal, run.budget = {"statement": "read the folder", "done_when": ["the script has been run on the folder"]}, 300
        os.makedirs(run._out_dir(), exist_ok=True)
        for name, text in files.items():
            Path(run._out_dir(), name).write_text(text)
        checks = [{"text": "s.py exists", "type": "file-exists", "target": "s.py", "expect": True}] + (
            [{"text": "its test passes", "type": "test-passed", "target": test, "expect": True}] if test else [])
        w = {"id": "W-1", "name": "reader", "purpose": "read", "outputs": [f"{FT}/s.py"], "status": status, "calls_used": attempts,
             "retries_used": 0, "cost": 10, "cycle": 1, "section": "W-1", "covers": [],
             "real_run": {"command": ["python3", "s.py", str(real)], "folder": str(real), "why": "read it", "checks": [1]},
             "atoms": [{"id": "W-1.a1", "goal": "read", "expected_output": [], "verification": checks}]}
        run.workflows = [w]
        j2env.add_workflow_agent("W-1")
        run.sites = ["v1"]
        run.post("user", "go")
        return run, w
    return made, real


def p42_builder(run, *rounds):
    """The run's builder, scripted: each call writes the next round's files (the last one again after that)."""
    prompts = []

    def call(fn, fmt, prompt, mock, **kw):
        prompts.append(prompt)
        for name, text in rounds[min(len(prompts), len(rounds)) - 1].items():
            Path(run._out_dir(), name).write_text(text)
        return {"say": "@Coordination built", "human_output": "I built the reader script and its test for the folder.", "atom_human_output": "The reader."}
    run.call = call
    return prompts


def p42_reply(run, text, **meta):
    h = run.paused["handoff"]
    run.post("user", text, **meta)
    run.paused = None
    run._turn_identity({**h, "answer": text})


def p42_receipts(run, kind="real_run"):
    path = Path(run.dir, "receipts.jsonl")
    return [r for r in map(json.loads, path.read_text().splitlines()) if r.get("type") == kind] if path.exists() else []


def p42_system(run):
    return [m["text"] for m in run.chat if m["who"] == "system"]


def p42_code(run):
    """The one-time code of the open install question: kept under "env:<hash>", where the snapshot reads it for the Run button."""
    key = run.paused["handoff"]["wid"]
    assert key.startswith("env:") and run.paused["handoff"]["kind"] == "env_install" and run.paused["kind"] == "real_run"
    assert run.snapshot()["paused"]["code"] == run.real_runs_asked[key]
    return run.real_runs_asked[key]


@p42_posix
def test_p42_requirements_get_an_environment_only_after_run_code_and_a_cached_one_is_reused(j2env, env_run, monkeypatch):
    made, real = env_run
    runenv = j2env.j2_runenv
    run, w = made({}, status="running", attempts=0, test="test_s.py")
    prompts = p42_builder(run, P42_FILES)
    run._turn_workflow_agent({"wid": "W-1"})
    plan, card, code = runenv.plan(run._out_dir()), p42_system(run)[-1], p42_code(run)
    assert run._auto_pick() is None and run.paused["handoff"]["build"] == "W-1" and run.paused["handoff"]["hash"] == plan["hash"]
    assert "pulsedep==1.2.0" in card and "from PyPI only" in card and f"RUN {code}" in card and "Nothing is installed until you approve" in card
    assert "Or press Run. To decline, press Don't run." in card
    assert plan["dir"].startswith(os.path.realpath(os.environ["J2_DATA_DIR"])) and str(run.dir) not in plan["dir"]
    # nothing is installed without approval
    assert not j2env.p42_log("venv") and not j2env.p42_log("pip install") and not os.path.exists(plan["dir"]) and not p42_receipts(run, "env_install")
    assert not any(x.get("check") == "its test passes" for x in run.receipts), "the test is not rerun before its packages are there"
    for text, meta in (("yes install", {}), (f"run {code}", {}), (f"RUN {code}", {"auto": True})):      # as D434: only the exact code
        p42_reply(run, text, **meta)
        assert run.paused and run.chat[-1]["who"] == "identity" and f"Not installed. Press Run or type RUN {code}." in run.chat[-1]["text"]
        assert p42_code(run) == code and not j2env.p42_log("pip install") and not p42_receipts(run, "env_install")
    p42_reply(run, f"RUN {code}")
    assert len(j2env.p42_log("venv")) == 1 and len(j2env.p42_log("pip install")) == 1 and not run.paused
    assert not [k for k in run.real_runs_asked if k.startswith("env:")], "the code is forgotten once it is answered"
    argv = j2env.p42_log("pip install")[0]["argv"]
    assert argv[argv.index("--index-url") + 1] == "https://pypi.org/simple" and "--isolated" in argv and "--extra-index-url" not in argv
    e = p42_receipts(run, "env_install")[-1]
    assert e["approved"] and e["exit"] == 0 and e["requirements_sha256"] == plan["hash"] and e["installed"] == {"pulsedep": "1.2.0"}
    assert e["python"] == runenv.env_python(plan["dir"]) and e["python_version"] and e["packages"] == ["pulsedep==1.2.0"] and e["workflow"] == "W-1"
    from sutra_app.library.records import _p_receipt
    assert [k for k, _ in _p_receipt("receipts.jsonl", e)] == ["run_file.object"], "the install receipt is open JSON for the catalogue"
    run._turn_workflow_agent(run.handoff)
    test = next(x for x in run.receipts if x["check"] == "its test passes")
    assert len(prompts) == 1 and w["status"] == "done" and test["pass"] is True and "resume" not in w
    assert any(m.get("human_output") == "I built the reader script and its test for the folder." for m in run.chat), "the builder's reply from before the question is kept"
    assert [r for r in j2env.p42_log("run") if r["python"] == runenv.env_python(plan["dir"]) and r["argv"] == ["test_s.py"]], \
        "the test rerun used the environment's python (the system one has no pulsedep)"
    # the dry run (fenced, D435) and the approved real run use the environment's python too
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", j2env.p42_srt)
    assert run._ask_real_run({}) and run.paused["handoff"]["kind"] == "real_run"
    assert any("uses packages installed in an environment of its own" in x and "pulsedep==1.2.0" in x for x in p42_system(run))
    assert "dry run on a copy: exit 0" in p42_system(run)[-1] and run.real_runs_dry["W-1"]["fenced"] is True
    p42_reply(run, f"RUN {run.real_runs_asked['W-1']}")
    r = p42_receipts(run)[-1]
    want = {"python": runenv.env_python(plan["dir"]), "requirements_sha256": plan["hash"], "installed": {"pulsedep": "1.2.0"}}
    assert r["approved"] and r["exit"] == 0 and {k: r["env"].get(k) for k in want} == want and r["env"]["python_version"]
    assert (real / "out.txt").read_text() == "1.2.0"
    monkeypatch.delenv("J2_SANDBOX")
    # a second run with the same requirements.txt reuses the environment: no question, no install
    n = len(j2env.p42_log("pip install"))
    run2, w2 = made({}, status="running", attempts=0, test="test_s.py")
    p42_builder(run2, P42_FILES)
    run2._turn_workflow_agent({"wid": "W-1"})
    assert not run2.paused and w2["status"] == "done" and not run2.real_runs_asked
    assert len(j2env.p42_log("pip install")) == n and len(j2env.p42_log("venv")) == 1
    assert next(x for x in run2.receipts if x["check"] == "its test passes")["pass"] is True
    # Don't run: nothing installed, the test is not rerun with another python, and the real run goes back to the build (D434)
    run3, w3 = made({}, status="running", attempts=0, test="test_s.py")
    p42_builder(run3, {**P42_FILES, "requirements.txt": "pulsedep==1.2.0\nextra-lib==0.3\n"})
    run3._turn_workflow_agent({"wid": "W-1"})
    assert run3.paused and "extra-lib==0.3" in p42_system(run3)[-1]
    p42_reply(run3, "don't run")
    d = p42_receipts(run3, "env_install")[-1]
    assert d["declined"] and not d["approved"] and d["evidence"] == "not installed: the Requester chose Don't run"
    run3._turn_workflow_agent(run3.handoff)
    t3 = [x for x in run3.receipts if x["check"] == "its test passes"][-1]
    assert len(j2env.p42_log("pip install")) == n and t3["pass"] is None and "its packages are not installed" in t3["evidence"]
    assert not run3.paused, "a declined requirements.txt is not asked about again in the run"
    w3["status"] = "done"
    assert run3._ask_real_run({}) is True and not run3.paused and "W-1" not in run3.real_runs_asked and not run3.real_runs_dry
    assert w3["status"] == "failed" and w3["failure"] == ["dry_run", "its packages are not installed: the Requester chose not to install them"]
    assert run3.turn == "adaptation" and p42_receipts(run3)[-1]["ran"] is False


@p42_posix
def test_p42_a_failed_install_goes_back_to_the_builder_with_pips_error(j2env, env_run, monkeypatch):
    made, real = env_run
    run, w = made({}, status="running", attempts=0, test="test_s.py")
    prompts = p42_builder(run, {**P42_FILES, "requirements.txt": "pulsedep==1.2.0\nnosuch==9.9\n"}, P42_FILES)
    run._turn_workflow_agent({"wid": "W-1"})
    j2env.p42_pip_fail.write_text("nosuch==9.9")
    try:
        p42_reply(run, f"RUN {p42_code(run)}")
    finally:
        j2env.p42_pip_fail.unlink()
    e = p42_receipts(run, "env_install")[-1]
    assert e["approved"] and e["exit"] == 1 and "No matching distribution found for nosuch==9.9" in e["stderr"]
    run._turn_workflow_agent(run.handoff)
    assert len(prompts) == 2 and "No matching distribution found for nosuch==9.9" in prompts[1] and "ATTEMPT 2 OF 3" in prompts[1]


def test_p42_a_missing_import_goes_back_to_the_build_and_bad_requirement_lines_are_refused(j2env, env_run, monkeypatch, tmp_path):
    made, real = env_run
    run, w = made({"s.py": "import sys\nimport notinstalledmod\nfrom helper import go\n", "helper.py": "def go():\n    pass\n"})
    assert run._ask_real_run({}) is True and not run.paused and "W-1" not in run.real_runs_asked and not run.real_runs_dry
    assert w["status"] == "failed" and w["failure"][0] == "dry_run" and run.turn == "adaptation"
    assert "s.py imports notinstalledmod, not installed" in w["failure"][1] and "requirements.txt" in w["failure"][1] and "helper" not in w["failure"][1]
    assert "notinstalledmod" in run.handoff["why"] and not p42_receipts(run)[-1]["ran"]
    run, w = made({}, status="running", attempts=0)
    prompts = p42_builder(run, *[{"s.py": P42_GOOD, "requirements.txt": text} for text in
                                 ("requests>=2\n", "--extra-index-url https://example.invalid/simple\npulsedep==1.2.0\n", "git+https://example.invalid/x.git\n")])
    n = len(j2env.p42_log("pip install"))
    run._turn_workflow_agent({"wid": "W-1"})
    assert len(prompts) == 3 and w["status"] == "failed" and not run.paused and not run.real_runs_asked and len(j2env.p42_log("pip install")) == n
    assert "requests>=2" in prompts[1] and "exact version" in prompts[1] and "--extra-index-url" in prompts[2]
    monkeypatch.setenv("J2_RUN_PYTHON", str(tmp_path / "no-such-python"))      # no interpreter: nothing is asked, nothing is run
    run, w = made({"s.py": P42_NEEDS, "requirements.txt": "pulsedep==7.0.0\n"})
    assert run._env_ask(w, 1, run._out_dir()) is False and run._ask_real_run({}) is True and not run.paused
    assert "which is not a Python that runs" in w["failure"][1] and "J2_RUN_PYTHON" in w["failure"][1]
    assert j2env.real_run(run._out_dir(), w["real_run"], 10)["ran"] is False, "never with another python"


@p42_posix
def test_p42_the_sandbox_opens_the_network_for_the_install_step_only(j2env, env_run, monkeypatch):
    made, real = env_run
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", j2env.p42_srt)
    run, w = made({}, status="running", attempts=0, test="test_s.py")
    p42_builder(run, {**P42_FILES, "requirements.txt": "pulsedep==1.2.0\nsandboxed==2.0\n"})
    before = len(j2env.p42_log("sandbox"))
    run._turn_workflow_agent({"wid": "W-1"})
    p42_reply(run, f"RUN {p42_code(run)}")
    run._turn_workflow_agent(run.handoff)
    run._ask_real_run({})
    p42_reply(run, f"RUN {run.real_runs_asked['W-1']}")
    rows = j2env.p42_log("sandbox")[before:]
    installs = [r for r in rows if " -m pip install " in r["command"]]
    others = [r for r in rows if r not in installs]
    env_dir = j2env.j2_runenv.plan(run._out_dir())["dir"]
    assert len(installs) == 1 and installs[0]["settings"]["network"]["allowedDomains"] == ["pypi.org", "files.pythonhosted.org"]
    assert installs[0]["settings"]["filesystem"]["allowWrite"] == [env_dir]
    assert len(others) == 3 and all(r["settings"]["network"]["allowedDomains"] == [] for r in others), "the test rerun, the dry run, the real run"
    assert all(env_dir in r["settings"]["filesystem"]["allowRead"] for r in others)
    assert p42_receipts(run)[-1]["exit"] == 0


def test_p42_a_real_run_receipt_keeps_the_end_of_stdout_and_of_stderr(j2env, env_run):
    made, real = env_run
    run, w = made({"s.py": "import sys\nprint('started')\nsys.stderr.write('x' * 3000 + 'LAST-LINE')\n"})
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run"      # no sandbox here: no dry run (D435), still asked
    p42_reply(run, f"RUN {run.real_runs_asked['W-1']}")
    r = p42_receipts(run)[-1]
    assert r["exit"] == 0 and r["stdout"] == "started\n" and len(r["stderr"]) == 2000 and r["stderr"].endswith("LAST-LINE")
    assert "env" not in r, "a build without a requirements.txt has no environment"
    from sutra_app.library.records import _p_receipt
    assert [k for k, _ in _p_receipt("receipts.jsonl", r)] == ["run_file.object"], "a real-run receipt stays open JSON for the catalogue"


def test_p42_runenv_is_j2s_module_below_its_docstring():
    """engine/runenv.py is Sutra's copy of J2's j2_runenv.py: the code is the same, only the module docstring differs. Skipped where
    the J2 prototype is not checked out beside this project."""
    theirs = Path(__file__).resolve().parents[3] / "prototypes" / "j2" / "j2_runenv.py"
    if not theirs.is_file():
        pytest.skip("prototypes/j2 is not here")
    code = lambda p: p.read_text(encoding="utf-8").split('"""\nimport ast', 1)[1]
    assert code(theirs) == code(Path(__file__).resolve().parents[2] / "sutra_app" / "engine" / "runenv.py")


# ---- P43 (D448): an answer never confirms a real-run item; a picked option counts with its full text, the Requester's only
P43_RR, P43_DOC = "The tool tidies the made-up folder for real", "A README explains how to run it"
P43_ANSWER = "It runs on ~/Documents/Made Up/Tool"
P43_LATER = "This part is checked when the real run actually happens, not from an answer."


def p43_answer(make_run, confirmed, planned=False, still=()):
    """Identity hears an answer to a fact question while the charter marks item 1 real-run (P30's item_checks)."""
    run = make_run()
    run.goal = {"statement": "x", "done_when": [P43_RR, P43_DOC],
                "item_checks": {P43_RR: {"type": "real-run"}, P43_DOC: {"type": "file-exists", "target": "README.md", "expect": True}},
                "to_be_confirmed": [{"criterion": P43_RR, "fact": "which folder it runs on"}]}
    run.workflows = [{"id": "W-1", "real_run": {"checks": [1]}}] if planned else []
    run.post("user", P43_ANSWER)
    run.call = lambda role, fmt, prompt, *a, **k: {"say": "ok", "to_requester": "Thanks.", "clause": "done_when", "confirmed": confirmed,
                                                   "still_to_be_confirmed": list(still), "next": "Adaptation"}
    run._identity_hears_requester({"asked": [{"question": "Which folder?"}], "answer": P43_ANSWER})
    return run


@pytest.mark.parametrize("planned", [False, True], ids=["unplanned", "planned"])
def test_p43_an_answer_never_confirms_a_real_run_item(make_run, planned):
    run = p43_answer(make_run, [{"item": 1, "fact": P43_ANSWER}], planned)
    texts = [m["text"] for m in run.chat]
    assert P43_RR not in {t["criterion"] for t in run.goal.get("confirmed_facts") or []}
    assert not any(t.startswith("Confirmed by the Requester") for t in texts)
    # review R1-2 (owner, option 1): an item not planned yet leaves to_be_confirmed, the fact is known; a planned one is J2's
    assert (P43_RR in {t["criterion"] for t in run.goal["to_be_confirmed"]}) is planned
    assert P43_ANSWER in run.handoff["why"], "the answer still reaches Adaptation"
    assert "~/documents/made up/tool" in run._fact_source()
    noted = [t for t in texts if t == "Noted. " + P43_LATER]
    planned_note = [t for t in texts if t.startswith("Not taken from the answer: whether a real run happened")]
    if planned:
        assert not noted and len(planned_note) == 1 and planned_note[0].endswith(". " + P43_LATER)
    else:
        assert len(noted) == 1 and not planned_note


def test_p43_an_answer_still_confirms_an_item_that_is_not_real_run(make_run):
    run = p43_answer(make_run, [{"item": 2, "fact": "README.md at the top"}])
    texts = [m["text"] for m in run.chat]
    assert P43_DOC in {t["criterion"] for t in run.goal.get("confirmed_facts") or []}
    assert f"Confirmed by the Requester: {P43_DOC} = README.md at the top" in texts
    assert not any(t.startswith("Noted.") for t in texts)


@pytest.fixture
def p43_pick(make_run, tmp_path, monkeypatch):
    """A run whose brief names no folder pauses on one question whose first option names a made-up folder."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    (tmp_path / "Documents" / "Made Up" / "Tool").mkdir(parents=True)
    run = make_run()
    run.request = "Build a tool that tidies a folder"
    run.goal = {"statement": "x", "done_when": [P43_DOC]}
    run._ask_user("Which folder?", [{"question": "Which folder should it run on?", "options": ["~/Documents/Made Up/Tool", "Another folder"],
                                     "kind": "decision"}], "fact", handoff={"kind": "requester_answered"}, done=False)
    monkeypatch.setattr(run, "_handoff", lambda *a, **k: setattr(run, "turn", None))
    monkeypatch.setattr(run, "_plan_stages", lambda: None)
    return run, run.paused["questions"][0]["options"][0]


@pytest.mark.parametrize("form", ["tilde", "written"])
@pytest.mark.parametrize("by", ["click", "auto"])
def test_p43_a_picked_option_names_its_folder_only_when_the_requester_picked_it(j2, p43_pick, by, form, monkeypatch):
    run, shown = p43_pick
    if by == "click":
        run.post("user", "Option 1")
        run._run()
    else:
        run.auto = True
        # P45 (D452): Decide for me no longer answers a question about the folder a real run uses; it waits for the Requester.
        # D448's own guard (a pick it did make never names a folder) is still checked below, with that subject rule set aside.
        assert run._auto_pick() is None and not any(m.get("auto") for m in run.chat)
        monkeypatch.setattr(run, "_requester_only", lambda p: None)
        run._auto_go()
        last = [m for m in run.chat if m["who"] == "user"][-1]
        assert last.get("auto") and last["text"] == "Option 1", "Decide for me picked the same option"
    folder = "~/Documents/Made Up/Tool" if form == "tilde" else os.path.expanduser("~/Documents/Made Up/Tool")
    rr = {"command": [sys.executable, "tool.py", folder], "folder": folder, "reads": [], "why": "x"}
    problems = j2.real_run_problems(rr, run._fact_source(), [sys.executable], run.dir)
    if by == "click":
        assert run.decisions[-1]["picked"] == shown
        assert problems == []
        assert run._fact_problems({"facts": [shown]}) == []
    else:      # D448: Decide for me never names a folder, a secret file or a charter fact; only the Requester does
        assert "picked" not in run.decisions[-1]
        assert any("not named" in p for p in problems)
        assert run._fact_problems({"facts": [shown]}) == [shown]


def test_p43_a_typed_answer_is_never_a_pick(p43_pick):
    run, _ = p43_pick
    run.post("user", "use 2 folders")
    run._run()
    assert run.decisions[-1]["answer"] == "use 2 folders" and "picked" not in run.decisions[-1]


def test_p43_r1_2_a_held_answer_clears_its_to_be_confirmed_entry_and_the_item_still_needs_a_receipt(make_run):
    """Review R1-2 (owner, option 1): the held answer gives the fact, so the item is no longer waiting on the Requester (never
    blocked, never asked again as a follow-up); it is still not confirmed and passes only on a real run's receipt."""
    run = p43_answer(make_run, [{"item": 1, "fact": P43_ANSWER}])
    assert P43_RR not in {t["criterion"] for t in run.goal["to_be_confirmed"]}
    assert P43_RR not in {t["criterion"] for t in run.goal.get("confirmed_facts") or []}
    run.audits = [{"results": [{"id": "F-1", "item": 1, "criterion": P43_RR, "verdict": "TO_BE_CONFIRMED", "pass": False},
                               {"id": "F-2", "item": 2, "criterion": P43_DOC, "verdict": "PASS", "pass": True}]}]
    assert run._blocked_items() == [] and run._tbc_blocked() == {}
    assert not any("Send it as a follow-up" in x for x in run._open_items())
    assert run._chain_done("Done.") == "Done.", "the run does not end asking for the fact it was given"
    assert run._run_item_check(P43_RR, {"type": "real-run"}, "", {})["pass"] is False, "no receipt: it does not pass"


def test_p43_r1_2_an_answer_that_cannot_give_the_fact_yet_keeps_the_entry(make_run):
    run = p43_answer(make_run, [], still=[{"item": 1, "fact": "which folder it runs on"}])
    assert P43_RR in {t["criterion"] for t in run.goal["to_be_confirmed"]}


P43_CSV = "CSV/Excel tidier for a folder"      # review R1-1: the brief's first word holds a "/"


@pytest.mark.parametrize("form", ["tilde", "written"])
@pytest.mark.parametrize("by", ["click", "typed"])
def test_p43_r1_1_a_folder_the_requester_names_registers_whatever_the_next_text_starts_with(sort_run, tmp_path, monkeypatch, by,
                                                                                            form):
    """Review R1-1: the brief, each answer and each pick are read one by one, so a path that ends one of them is never read as
    going on into the next one's first word ("CSV/Excel")."""
    d448_home(tmp_path, monkeypatch)
    (tmp_path / "Documents" / "Made Up" / "Tool").mkdir(parents=True)
    (tmp_path / "Documents" / "Made Up" / "key.txt").write_text("x")
    make, _ = sort_run
    run = make()
    run.request = P43_CSV
    run.post("user", P43_CSV)
    if by == "click":
        run._ask_user("Which folder?", [{"question": "Which folder should it run on?", "options": ["~/Documents/Made Up/Tool",
                                                                                                    "Another folder"],
                                         "kind": "decision"}], "fact", handoff={"kind": "requester_answered"}, done=False)
        monkeypatch.setattr(run, "_handoff", lambda *a, **k: setattr(run, "turn", None))
        monkeypatch.setattr(run, "_plan_stages", lambda: None)
        run.post("user", "Option 1")
        run._run()
        assert run.decisions[-1]["picked"] == "~/Documents/Made Up/Tool"
    else:      # typed answers, each followed by a Requester message whose first word holds a "/"
        for said in ("It runs on ~/Documents/Made Up/Tool", "It reads ~/Documents/Made Up/key.txt"):
            run.post("user", said)
            run.post("user", "CSV/Excel files only, please")
    folder = "~/Documents/Made Up/Tool" if form == "tilde" else os.path.expanduser("~/Documents/Made Up/Tool")
    w = sort_proposals(folder, fix=True)[0]
    rr = {**w["real_run"], "command": ["python3", "sort_files.py", folder], "folder": folder}
    if by == "typed":
        rr["secret_files"] = {"API_KEY_FILE": folder.replace("Tool", "key.txt")}
    reg, refused, _ = run._register([{**w, "real_run": rr}])
    assert [x["id"] for x in reg] == ["W-1"] and not refused, refused


# ---- P31, P41 amended (D448): a folder or secret file is named only whole (named_whole: one rule for both checks)
D448_WHOLE = [      # (path, what the brief says, named whole?): made-up paths only
    ("~/Documents/Made", "use ~/Documents/Made Up/Tool", False),
    ("~/Documents/Made Up/Tool", "use ~/Documents/Made Up/Tool", True),
    ("~/Documents/Made Up/Tool", "is it ~/Documents/Made Up/Tool?", True),
    ("~/Documents/Made Up/Tool", "yes ~/Documents/Made Up/Tool! now", True),
    ("~/Documents/Made Up/Tool", "the folder `~/Documents/Made Up/Tool` please", True),
    ("~/Documents/Made Up/Tool", "~/Documents/Made Up/Tool/ and more", True),
    ("~/demo/rename-test", "run it on ~/demo/rename-test", True),
    ("~/demo/x", "run on ~/demo/x and ~/demo/y", True),
    ("~/demo/x", "run on ~/demo/x, then stop.", True),
    ("~/demo/x", "run on ~/demo/x. then stop", True),
    ("~/demo/x", "run on ~/demo/xy", False),
    ("/projects/x", "use /data/projects/x now", False),      # inside a longer path
    ("~/demo/x", "folder=~/demo/x", True),
    ("~/demo/x", "(~/demo/x)", True),
    ("~/demo/x", "'~/demo/x'", True),
    ("~/demo/x", "use ~/demo/x w/ care", False),      # known limit: a next word holding "/" reads as the path going on (fails safe)
]


def d448_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))      # Windows: expanduser reads USERPROFILE


def test_p31_d448_a_folder_is_named_only_whole(j2, tmp_path, monkeypatch):
    d448_home(tmp_path, monkeypatch)
    for d in (("Documents", "Made"), ("Documents", "Made Up", "Tool"), ("projects", "x")):
        tmp_path.joinpath(*d).mkdir(parents=True)

    def not_named(folder, said):
        rr = {"command": [sys.executable, "tool.py"], "folder": folder, "reads": [], "why": "x"}
        return any("is not named" in p for p in j2.real_run_problems(rr, j2.squash(said), [sys.executable], str(tmp_path / "run")))
    assert not_named("~/Documents/Made", "use ~/Documents/Made Up/Tool"), "a parent of the named folder is not named"
    for said in ("is it ~/Documents/Made Up/Tool?", "yes ~/Documents/Made Up/Tool! now", "the folder `~/Documents/Made Up/Tool` please"):
        assert not not_named("~/Documents/Made Up/Tool", said), said
    inner = str(tmp_path / "projects" / "x")
    assert not_named(inner, f"use /data{inner} now"), "a path inside a longer one is not named"
    for g, said, want in D448_WHOLE:
        assert j2.named_whole(g, j2.squash(said)) is want, (g, said)


def test_p41_d448_a_secret_file_is_named_only_whole(j2, tmp_path, monkeypatch):
    d448_home(tmp_path, monkeypatch)
    (tmp_path / "Documents" / "Made Up").mkdir(parents=True)
    (tmp_path / "Documents" / "Made").write_text("x")
    (tmp_path / "Documents" / "Made Up" / "key.txt").write_text("x")

    def not_named(f, said):
        return any("is not named" in p for p in j2.real_run_env_problems({"secret_files": {"API_KEY_FILE": f}}, j2.squash(said),
                                                                          str(tmp_path / "run")))
    assert not_named("~/Documents/Made", "read ~/Documents/Made Up/key.txt"), "a shorter file is not named"
    for said in ("read `~/Documents/Made Up/key.txt`?", "is it ~/Documents/Made Up/key.txt?", "yes ~/Documents/Made Up/key.txt! now"):
        assert not not_named("~/Documents/Made Up/key.txt", said), said


# ---- P44 (D449): a real run's internet hosts; the dry run runs an offline command ----------------------------------------------
# Made-up hosts only (.invalid, RFC 2606); nothing here resolves a name or reaches the internet.
P44_DONE_WHEN = ["fetch.py saves the page title", "A test covers fetch.py with a fake server", "fetch.py ran for real on the folder"]
P44_URL = "http://api.made-up.invalid/v1"
MISSING, DEFAULT = object(), object()      # a field left out of the plan; the fixture's default value


@pytest.fixture
def p44_reg(j2ft, tmp_path, monkeypatch):
    """new(request, goal, runner): a fresh run of the folder type whose brief names the made-up folder and host;
    register(run, hosts, offline, folder, **fields): W-1 proposed with a real run on that folder: (run, registered, refused)."""
    dst, home = tmp_path / "out", tmp_path / "home"
    dst.mkdir()
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))      # Windows: expanduser reads USERPROFILE
    counter = itertools.count(1)

    def new(request=None, goal=None, runner=None):
        run = j2ft.J2Run(run_dir=tmp_path / "runs" / f"j2-20261125-1000{next(counter):02d}-5e12")
        run._apply_output(FT)
        if runner:
            run.out = {**run.out, "test_runner": runner}
        run.request = request or f"Build fetch.py and run it on {dst}: it reads {P44_URL} and writes title.txt"
        run.goal, run.budget = goal or {"statement": "x", "done_when": list(P44_DONE_WHEN)}, 100
        return run

    def proposal(run, hosts=DEFAULT, offline=DEFAULT, folder=None, **fields):
        x, f = run.out["test_runner"][0], folder or str(dst)
        rr = {"command": [x, "fetch.py", f, P44_URL], "folder": f, "reads": [], "why": "x", "checks": [3],
              "expect": {"created": ["title.txt"], "changed": [], "deleted": []},
              "hosts": ["api.made-up.invalid"] if hosts is DEFAULT else hosts,
              "offline": {"command": [x, "fetch.py", f, "--offline"], "same_files": True} if offline is DEFAULT else offline,
              **fields}
        return [{**sort_proposals(f, fix=True)[0], "real_run": {k: v for k, v in rr.items() if v is not MISSING}}]

    def register(run=None, **kw):
        run = run or new()
        reg, refused, _ = run._register(proposal(run, **kw))
        return run, reg, refused
    return SimpleNamespace(new=new, proposal=proposal, register=register, dst=dst, home=home)


def test_p44_a_good_plan_registers_hosts_and_offline(p44_reg):
    run, reg, refused = p44_reg.register(hosts=[" API.Made-Up.invalid ", "api.made-up.invalid"])
    assert len(reg) == 1 and not refused, refused
    x = run.out["test_runner"][0]
    assert reg[0]["real_run"]["hosts"] == ["api.made-up.invalid"]      # lower case, each once (Kaivan's real_hosts)
    assert reg[0]["real_run"]["offline"] == {"command": [x, "fetch.py", str(p44_reg.dst), "--offline"], "same_files": True}
    run, reg, refused = p44_reg.register(hosts=MISSING, offline=MISSING)
    assert len(reg) == 1 and not {"hosts", "offline"} & set(reg[0]["real_run"]), reg[0]["real_run"]
    run, reg, refused = p44_reg.register(hosts=MISSING)      # offline without hosts is not stored
    assert len(reg) == 1 and "offline" not in reg[0]["real_run"], reg[0]["real_run"]
    (p44_reg.home / "x").mkdir()
    run = p44_reg.new(request=f"Build fetch.py and run it on ~/x: it reads {P44_URL}")
    run, reg, refused = p44_reg.register(run, folder="~/x", offline={"command": [x, "fetch.py", "~/x", "--offline"], "same_files": False})
    assert len(reg) == 1 and not refused, refused
    assert reg[0]["real_run"]["offline"] == {"command": [x, "fetch.py", os.path.expanduser("~/x"), "--offline"], "same_files": False}


@pytest.mark.parametrize("case, want", [
    ("missing", 'also needs "offline"'), ("no_same_files", "must be exactly"), ("same_files_text", "must be exactly"),
    ("real_command", "is the real command"), ("no_folder", "offline: real_run command must pass the folder")])
def test_p44_hosts_without_offline_are_refused_with_their_key(p44_reg, case, want):
    x, f = "python3", str(p44_reg.dst)
    offline = {"missing": MISSING, "no_same_files": {"command": [x, "fetch.py", f, "--offline"]},
               "same_files_text": {"command": [x, "fetch.py", f, "--offline"], "same_files": "yes"},
               "real_command": {"command": [x, "fetch.py", f, P44_URL], "same_files": True},
               "no_folder": {"command": [x, "fetch.py", "--offline"], "same_files": True}}[case]
    run, reg, refused = p44_reg.register(offline=offline)
    assert not reg and len(refused) == 1 and run.rejections[-1]["key"] == ["real_run_offline"], refused
    assert want in refused[0] and (case != "no_folder" or "offline: real_run command must pass the folder" in run.rejections[-1]["reason"])


@pytest.mark.parametrize("host, ok", [
    ("https://api.made-up.invalid", False), ("api.made-up.invalid/v1", False), ("*", False), ("*.invalid", False),
    ("10.0.0.8", False), ("localhost", False), ("api.made-up.invalid:0", False), ("api.made-up.invalid:65536", False),
    ("api.made-up.invalid:08", False), ("made-up", False), (5, False),
    ("*.made-up.invalid", True), ("api.made-up.invalid:8443", True)])
def test_p44_host_format_refused_and_accepted(p44_reg, host, ok):
    run = p44_reg.new(request=f"Build fetch.py and run it on {p44_reg.dst}: it reads {host} and {P44_URL}")
    run, reg, refused = p44_reg.register(run, hosts=[host])
    if ok:
        assert len(reg) == 1 and reg[0]["real_run"]["hosts"] == [host], refused
        return
    assert not reg and run.rejections[-1]["key"] == ["real_run_hosts"], refused
    assert ("must be a list of host names" if host == 5 else "must be a host name") in refused[0], refused


def test_p44_host_named_only_whole_in_brief_typed_or_picked(j2ft):
    named = lambda h, *pieces: j2ft.host_named(h, [j2ft.squash(p) for p in pieces])
    for said in ("https://api.made-up.invalid/v1 and", "api.made-up.invalid:8443/x", "api.made-up.invalid.", "(api.made-up.invalid)"):
        assert named("api.made-up.invalid", said), said
    for said in ("x.api.made-up.invalid", "notapi.made-up.invalid", "api.made-up.invalid.evil.example", "bob@api.made-up.invalid",
                 "*.api.made-up.invalid"):
        assert not named("api.made-up.invalid", said), said
    assert named("api.made-up.invalid:8443", "use api.made-up.invalid"), "a port only narrows: it need not be written"
    assert named("*.made-up.invalid", "use *.made-up.invalid") and not named("*.made-up.invalid", "made-up.invalid")
    assert not named("api.made-up.invalid", "api.made-", "up.invalid"), "a host split across two texts is not named"


def p44_option(run, monkeypatch):
    """P43's option setup: one decision question whose first option names the made-up host."""
    run._ask_user("Which host?", [{"question": "Which host should it reach?", "options": ["Use api.made-up.invalid", "Another host"],
                                   "kind": "decision"}], "fact", handoff={"kind": "requester_answered"}, done=False)
    monkeypatch.setattr(run, "_handoff", lambda *a, **k: setattr(run, "turn", None))
    monkeypatch.setattr(run, "_plan_stages", lambda: None)


def test_p44_host_only_in_charter_or_decide_for_me_is_refused(p44_reg, monkeypatch):
    """Owner answer 1: the charter (an agent writes it) and Decide for me never name a host; _fact_source would have."""
    brief = f"Build fetch.py and run it on {p44_reg.dst}"
    goal = {"statement": "x", "done_when": ["fetch.py saves the page title of api.made-up.invalid"] + P44_DONE_WHEN[1:]}
    run, reg, refused = p44_reg.register(p44_reg.new(request=brief, goal=goal))
    assert not reg and run.rejections[-1]["key"] == ["real_run_hosts"] and "not named" in refused[0], refused
    assert "api.made-up.invalid" in run._fact_source()
    run = p44_reg.new(request=brief)
    p44_option(run, monkeypatch)
    run.auto = True
    run._auto_go()
    assert [m for m in run.chat if m["who"] == "user"][-1].get("auto") and "picked" not in run.decisions[-1]
    run, reg, refused = p44_reg.register(run)
    assert not reg and run.rejections[-1]["key"] == ["real_run_hosts"], refused
    run = p44_reg.new(request=brief)
    run.post("user", "api.made-up.invalid", auto=True)
    run, reg, refused = p44_reg.register(run)
    assert not reg and run.rejections[-1]["key"] == ["real_run_hosts"], refused


def test_p44_host_in_a_requester_click_registers(p44_reg, monkeypatch):
    brief = f"Build fetch.py and run it on {p44_reg.dst}"
    run = p44_reg.new(request=brief)
    p44_option(run, monkeypatch)
    run.post("user", "Option 1")
    run._run()
    assert run.decisions[-1]["picked"] == "Use api.made-up.invalid"
    run, reg, refused = p44_reg.register(run)
    assert len(reg) == 1 and not refused and reg[0]["real_run"]["hosts"] == ["api.made-up.invalid"], refused
    run = p44_reg.new(request=brief)
    run.post("user", "it calls api.made-up.invalid")
    run, reg, refused = p44_reg.register(run)
    assert len(reg) == 1 and not refused and reg[0]["real_run"]["hosts"] == ["api.made-up.invalid"], refused


# ---- P44 (D449) T1b (owner): hosts the Requester has not named are asked once, in a pickable option; never Decide for me
def p44_flow(run, monkeypatch, *proposals):
    """Adaptation's proposals, one per Adaptation turn, registered by the validator's own _agree; any other turn (building)
    ends the run here."""
    it = iter(proposals)

    def turn():
        if run.turn == "adaptation":
            run._agree(next(it))
        else:
            run.turn = None
    monkeypatch.setattr(run, "_dispatch_turn", turn)


def p44_asked(run):
    return [m for m in run.chat if m.get("pause") == "hosts"]


@pytest.fixture
def p44_ask(p44_reg, monkeypatch):
    """A run whose brief names the folder but no host; Adaptation's plan names the made-up host: the validator refuses it and
    Identity asks the host question. Returns (run, the question, proposal(**fields) for later turns)."""
    def go(*later, runner=None, **fields):
        run = p44_reg.new(request=f"Build fetch.py and run it on {p44_reg.dst}", runner=runner)
        plan = p44_reg.proposal(run, **fields)
        p44_flow(run, monkeypatch, plan, *[x if x is not None else plan for x in later])
        run.post("user", "Build it, please")
        run._run()
        assert not run.workflows and run.rejections[-1]["key"] == ["real_run_hosts"], run.rejections
        assert len(p44_asked(run)) == 1 and run.paused["kind"] == "hosts", [m["text"] for m in run.chat]
        return run, run.paused["questions"][0], plan
    return go


def test_p44_t1b_unnamed_hosts_are_asked_once_and_the_requesters_click_registers_them(p44_ask, p44):
    run, q, _ = p44_ask(None, reaches="the made-up API", runner=[sys.executable, "{target}"])      # p44: the fake srt
    assert q["question"] == "This script needs to reach the made-up API (api.made-up.invalid). Allow it?", q
    assert q["options"] == ["Allow internet access to api.made-up.invalid", "Don't allow it: leave the real run out"], q
    run.post("user", "Option 1")      # what a card click sends
    run._run()
    assert run.decisions[-1]["picked"] == "Allow internet access to api.made-up.invalid"
    assert [w["real_run"]["hosts"] for w in run.workflows] == [["api.made-up.invalid"]], run.rejections
    assert len(p44_asked(run)) == 1 and run.paused is None, "no second question"
    assert run.hosts_asked == {"api.made-up.invalid": True} and run.hosts_ask is None
    run.workflows[0]["status"] = "done"      # T3: once built, the Run card shows the hosts the Requester's click allowed
    os.makedirs(run._out_dir(), exist_ok=True)
    (Path(run._out_dir()) / "fetch.py").write_text(P44_FETCH)
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run", [m["text"] for m in run.chat]
    assert "\nInternet access: api.made-up.invalid" in p32_card(run)


def test_p44_t1b_without_reaches_the_question_names_the_hosts_alone(p44_ask):
    _, q, _ = p44_ask(hosts=["api.made-up.invalid", "*.cdn.made-up.invalid:8443"], reaches="two\nlines")
    assert q["question"] == "This script needs to reach api.made-up.invalid, *.cdn.made-up.invalid:8443. Allow it?", q
    assert q["options"][0] == "Allow internet access to api.made-up.invalid, *.cdn.made-up.invalid:8443"


@pytest.mark.parametrize("answer", ["Option 2", "  don't ALLOW "])      # the Don't allow button (E29) or its exact text
def test_p44_t1b_a_decline_leaves_the_real_run_out_with_the_reason_and_never_asks_again(p44_ask, answer):
    without = [{**sort_proposals("x", fix=True)[0], "real_run": None}]      # Adaptation's plan without the real run
    run, q, plan = p44_ask(None, without)      # it first proposes the same hosts again: refused, not asked again
    run.post("user", answer)
    run._run()
    why = "The Requester did not allow internet access to api.made-up.invalid"
    assert ("picked" in run.decisions[-1]) == (answer == "Option 2") and len(p44_asked(run)) == 1 and run.paused is None
    assert run.goal["done_when"] == P44_DONE_WHEN[:2]
    assert run.goal["dropped_reasons"] == [{"criterion": P44_DONE_WHEN[2], "reason": why, "hosts": ["api.made-up.invalid"]}]
    assert any(m["text"].startswith("Left out on the Requester's decision") and why.lower() in m["text"].lower() for m in run.chat)
    assert [w.get("real_run") for w in run.workflows] == [None], run.rejections      # registered without its real run
    run._goal_done({})
    assert f"Left out: {P44_DONE_WHEN[2]}: {why}." in run.outcome, run.outcome
    run._hosts_to_ask("Build sort_files.py", plan[0]["real_run"])      # the same hosts in a later plan: never asked again
    assert run.hosts_ask is None and run.hosts_asked == {"api.made-up.invalid": False}


@pytest.mark.parametrize("answer", ["yes", "Don't allow it, thanks", "allow", "Option 3"])
def test_p44_t1b_any_other_answer_keeps_the_host_question_open(p44_ask, answer):
    """Owner (E29): only the Allow pick, the hosts typed out, or a clear decline settle it; code reads no other word."""
    run, q, _ = p44_ask()      # no later proposal: a handoff to Adaptation would end the test with StopIteration
    run.post("user", answer)
    run._run()
    asked = p44_asked(run)
    assert run.paused["kind"] == "hosts" and run.paused["questions"] == [q], run.paused
    assert "Not allowed yet. Press Allow, or type the hosts." in asked[-1]["text"], asked[-1]["text"]
    assert run.paused["handoff"]["hosts_ask"]["hosts"] == ["api.made-up.invalid"]
    assert run.hosts_asked == {"api.made-up.invalid": None} and not run.workflows and "dropped_reasons" not in run.goal
    assert not p31_receipts(run) and not any(m["text"].startswith("Left out") for m in run.chat)


def test_p44_t1b_the_hosts_typed_out_register(p44_ask):
    """Passes before E29 too: typed hosts already counted (T1); pinned beside the stricter answers."""
    run, _, _ = p44_ask(None)
    run.post("user", "yes, api.made-up.invalid")
    run._run()
    assert [w["real_run"]["hosts"] for w in run.workflows] == [["api.made-up.invalid"]], run.rejections
    assert run.paused is None and run.hosts_asked == {"api.made-up.invalid": True}


@pytest.mark.parametrize("answer", ["Option 1", "Option 2"])
def test_p44_t1b_the_host_question_loses_no_other_workflow_of_its_batch(p44_reg, monkeypatch, answer):
    """R1-4: one batch registers a workflow without hosts and asks about the other's. The question takes coordination's
    schedule turn; after the answer the batch-mate is still registered and coordination still schedules it."""
    run = p44_reg.new(request=f"Build fetch.py and run it on {p44_reg.dst}")
    hosted, other = p44_reg.proposal(run)[0], {**sort_proposals("x")[1], "dependencies": []}
    again = hosted if answer == "Option 1" else {**hosted, "real_run": None}
    it, turns = iter([[hosted, other], [again]]), []

    def turn():
        turns.append((run.turn, run.handoff.get("kind")))
        if run.turn == "adaptation":
            run._agree(next(it))
        else:
            run.turn = None
    monkeypatch.setattr(run, "_dispatch_turn", turn)
    run.post("user", "Build it, please")
    run._run()
    assert run.paused["kind"] == "hosts" and [w["name"] for w in run.workflows] == [other["name"]], run.rejections
    assert ("coordination", "schedule") not in turns, turns
    run.post("user", answer)
    run._run()
    assert run.paused is None and turns[-1] == ("coordination", "schedule"), turns
    assert sorted(w["name"] for w in run.workflows) == sorted([other["name"], hosted["name"]]), run.rejections
    assert all(w["status"] == "registered" for w in run.workflows), run.workflows


def test_p44_t1b_a_document_run_asks_about_the_hosts_as_written(p44_reg, monkeypatch):
    """R1-1: a document run's "site" -> "document" rewrite never touches the host question; else Allow named a host that
    isn't the plan's and asked again on every press."""
    run = p44_reg.new(request=f"Build fetch.py and run it on {p44_reg.dst}")
    run.doc = True      # a document run (its form has a template) that asks for no page
    assert run._requester_noun("sites.made-up.invalid") == "documents.made-up.invalid"      # the rewrite this test guards
    run._hosts_to_ask("Build sort_files.py", p44_reg.proposal(run, hosts=["sites.made-up.invalid"])[0]["real_run"])
    a, run.hosts_ask = run.hosts_ask, None      # as _run's loop takes it
    run._ask_hosts(a)
    q = run.paused["questions"][0]
    assert q["options"][0] == "Allow internet access to sites.made-up.invalid" and "sites.made-up.invalid" in q["question"], q
    monkeypatch.setattr(run, "_dispatch_turn", lambda: setattr(run, "turn", None))
    run.doc = False      # the folder fixture has no document file for the run's end (summary.json); the pick is already made
    run.post("user", "Option 1")
    run._run()
    assert run.paused is None and run.hosts_asked == {"sites.made-up.invalid": True} and len(p44_asked(run)) == 1, run.paused


def test_p44_t1b_decide_for_me_never_answers_the_host_question(p44_ask, j2ft):
    run, _, _ = p44_ask()
    assert "hosts" in j2ft.AUTO_ASK
    run.auto = True
    run._auto_go()
    assert run.paused["kind"] == "hosts" and not [m for m in run.chat if m.get("auto")], "it waits for the Requester"
    assert run.snapshot()["paused"]["auto_waits"] is True

# ---- P44 (D449) T2: the dry run runs the offline command, offline; only the approved real run reaches the named hosts --------
# Made-up script: offline it writes a made-up title; for real it fetches the URL it was given (through the sandbox's proxy).
P44_FETCH = ("import os, sys, urllib.request\nf, src = sys.argv[1], sys.argv[2]\n"
             "body = '<title>made-up</title>' if src == '--offline' else urllib.request.urlopen(src, timeout=5).read().decode()\n"
             "open(os.path.join(f, 'title.txt'), 'w').write(body)\n")
# Made-up stand-in for srt (test only, no sandbox): it records the allowedDomains and the -c command it was given, then runs the
# command (a list, never a shell) with HTTP_PROXY at its own 127.0.0.1 proxy. The proxy serves a made-up page itself for an
# allowed host (exact, or *.x for a strict subdomain; ports dropped) and answers 403 for any other, as srt does; nothing is forwarded,
# no name is resolved (urllib sends the absolute URI to the proxy).
P44_SRT = r'''import http.server, json, os, shlex, subprocess, sys, threading, urllib.parse
a = sys.argv[1:]
allowed = json.load(open(a[a.index("-s") + 1]))["network"]["allowedDomains"]
cmd = a[a.index("-c") + 1]
with open(sys.argv[0] + ".net.jsonl", "a") as f:
    f.write(json.dumps({"allowedDomains": allowed, "command": cmd}) + "\n")
def ok(h):
    for e in allowed:
        e = e.rsplit(":", 1)[0]
        if h == e or (e.startswith("*.") and h.endswith(e[1:])):
            return True
    return False
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if ok(urllib.parse.urlsplit(self.path).hostname or ""):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<title>made-up</title>")
        else:
            self.do_CONNECT()
    def do_CONNECT(self):
        self.send_response(403)      # srt 0.0.81 answers a plain-HTTP GET 403 Forbidden
        self.end_headers()
    def log_message(self, *x):
        pass
s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=s.serve_forever, daemon=True).start()
p = "http://127.0.0.1:%d" % s.server_port
sys.exit(subprocess.run(shlex.split(cmd), env={**os.environ, "HTTP_PROXY": p, "http_proxy": p}).returncode)
'''


def p44_net(seen):
    return [json.loads(x) for x in seen.read_text().splitlines()] if seen.exists() else []


@pytest.fixture
def p44(p44_reg, tmp_path, monkeypatch):
    """go(script, request, **register fields): W-1 (fetch.py, its real run on the made-up folder, item 3) registered with
    sys.executable as the runner, done, its script written; the dry run and the real run go through the fake srt. Returns
    (go, the real folder, where the fake srt records what it was given)."""
    fake = tmp_path / "fake_srt.py"
    fake.write_text(P44_SRT)
    monkeypatch.setenv("J2_SANDBOX", "1")
    monkeypatch.setenv("J2_SANDBOX_CMD", shlex.join([sys.executable, str(fake)]))      # split back exactly, on any OS

    def go(script=P44_FETCH, request=None, **fields):
        run = p44_reg.new(request=request, runner=[sys.executable, "{target}"])
        run, reg, refused = p44_reg.register(run, **fields)
        assert [w["id"] for w in reg] == ["W-1"] and not refused, refused
        run.workflows[0]["status"] = "done"
        os.makedirs(run._out_dir(), exist_ok=True)
        (Path(run._out_dir()) / "fetch.py").write_text(script)
        run.post("user", "Build it and run it on my folder")
        return run
    return go, p44_reg.dst, Path(str(fake) + ".net.jsonl")


def test_p44_the_dry_run_runs_the_offline_command_without_network(p44):
    go, real, seen = p44
    run = go()
    assert run._ask_real_run({}) is True and run.paused["kind"] == "real_run", [m["text"] for m in run.chat]
    net = p44_net(seen)
    assert len(net) == 1 and net[0]["allowedDomains"] == [], net
    assert "--offline" in net[0]["command"] and "api.made-up.invalid" not in net[0]["command"]
    dry = run.real_runs_dry["W-1"]
    assert dry["exit"] == 0 and dry["created"] == ["title.txt"], dry
    assert not (real / "title.txt").exists()


@pytest.mark.parametrize("hosts", [["api.made-up.invalid"], ["api.made-up.invalid", "*.cdn.made-up.invalid:8443"]])
def test_p44_the_real_run_gets_exactly_the_hosts(p44, hosts):
    go, real, seen = p44
    run = go(request=f"Build fetch.py and run it on {real}: it reads {P44_URL} and *.cdn.made-up.invalid", hosts=hosts)
    assert run._ask_real_run({}) is True and run.paused["kind"] == "real_run"
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    assert p44_net(seen)[-1]["allowedDomains"] == hosts
    r = p31_receipts(run)[-1]
    assert r["approved"] and r["ran"] and r["exit"] == 0 and r["hosts"] == hosts and "offline" in r, r
    assert (real / "title.txt").read_text() == "<title>made-up</title>"


def test_p44_a_host_not_named_is_refused_in_the_real_run(p44):
    """Fails closed: the approved real run reaches only its hosts; any other gets the sandbox's 403."""
    go, real, seen = p44
    run = go(P44_FETCH.replace("urlopen(src,", "urlopen('http://other.made-up.invalid/',"))
    run._ask_real_run({})
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    r = p31_receipts(run)[-1]
    assert p44_net(seen)[-1]["allowedDomains"] == ["api.made-up.invalid"]
    assert r["approved"] and r["exit"] != 0 and "403" in r["output"] and not (real / "title.txt").exists(), r


def test_p44_a_networked_command_in_the_dry_run_never_gets_hosts(j2ft, p44):
    """A guard of P32's fence: the dry run of a networked command gets no host even when the run it is given names hosts. It
    passes before and after P44 (the fence was already there); it pins that Edit C keeps it."""
    go, real, seen = p44
    run = go()
    rr = {**run.workflows[0]["real_run"], "command": [sys.executable, "fetch.py", str(real), P44_URL]}
    dry = j2ft.real_run_dry(run._out_dir(), rr, 30)
    assert p44_net(seen)[-1]["allowedDomains"] == [] and dry["exit"] != 0 and "403" in dry["output"], dry


def test_p44_rerun_and_install_keep_their_network(j2ft):
    assert j2ft.sandbox_settings("/x")["network"]["allowedDomains"] == []
    assert j2ft.j2_runenv.PYPI_HOSTS == ("pypi.org", "files.pythonhosted.org")


def p44_real_srt(p44, monkeypatch, tmp_path):
    """The real srt (no network is reached: srt's proxy refuses a name not on its list with 403, observed as "HTTP Error 403:
    Forbidden" for a plain-HTTP GET; a .invalid name never resolves), with a temp HOME as P41's real-srt tests have (srt
    denies reads under ~). The dry-run test passes before P44 too: P32's fence already held."""
    go, real, _ = p44
    run = go()
    home = tmp_path / "srt-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("J2_SANDBOX_CMD", "srt")
    return run, real


@pytest.mark.skipif(shutil.which("srt") is None or not sys.platform.startswith(("darwin", "linux")), reason="needs the sandbox runtime")
def test_p44_real_srt_dry_run_refuses_a_named_host(j2ft, p44, monkeypatch, tmp_path):
    run, real = p44_real_srt(p44, monkeypatch, tmp_path)
    rr = {**run.workflows[0]["real_run"], "command": [sys.executable, "fetch.py", str(real), P44_URL]}
    dry = j2ft.real_run_dry(run._out_dir(), rr, 60)
    assert dry["ran"] and dry["exit"] != 0 and "HTTP Error 403" in dry["output"], dry      # srt's proxy refused the name


@pytest.mark.skipif(shutil.which("srt") is None or not sys.platform.startswith(("darwin", "linux")), reason="needs the sandbox runtime")
def test_p44_real_srt_takes_the_hosts_and_still_refuses_others(j2ft, p44, monkeypatch, tmp_path):
    """srt starts with a P44 hosts list (a wildcard with a port) and still refuses a host not on it. The allowed path is not
    tested with the real srt: it would resolve a name. Passes before Edit C too (an empty list refuses the same host)."""
    run, real = p44_real_srt(p44, monkeypatch, tmp_path)
    rr = {**run.workflows[0]["real_run"], "hosts": ["*.made-up.invalid:8443"],
          "command": [sys.executable, "fetch.py", str(real), "http://other.invalid/"]}
    res = j2ft.real_run(run._out_dir(), rr, 60)
    assert res["ran"] and "in the sandbox" in res["evidence"] and "HTTP Error 403" in res["output"], res

# ---- P44 (D449) T3: the Run card names the internet hosts and what the dry run could not check ------------------------------
P44_LOCAL = "import os, sys\nopen(os.path.join(sys.argv[1], 'title.txt'), 'w').write('made-up')\n"      # reaches nothing


def test_p44_card_lines(p44, monkeypatch):
    go, real, _ = p44
    run = go()
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run"
    card = p32_card(run)
    off = shlex.join([sys.executable, "fetch.py", str(real), "--offline"])
    assert "\nInternet access: api.made-up.invalid" in card and "can't be limited" not in card, card
    assert "\nThe dry run ran its offline command, without internet access: " + off in card, card
    monkeypatch.setenv("J2_SANDBOX", "0")      # no sandbox for the real run; P32 still fences the dry run (the fake srt)
    run = go()
    assert run._ask_real_run({}) and run.real_runs_dry["W-1"]["fenced"] is True
    card = p32_card(run)
    assert "\nThis computer has no sandbox, so internet access can't be limited to these hosts." in card, card
    assert "\nThe dry run ran its offline command" in card
    monkeypatch.setenv("J2_SANDBOX_CMD", "no-such-sandbox-xyz")      # no runtime at all: no dry run
    run = go()
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run"
    card = p32_card(run)
    assert NO_DRY_RUN in card and "can't be limited to these hosts" in card and "offline command" not in card, card


def test_p44_no_hosts_card_is_unchanged(j2ft, p44):
    assert j2ft.real_run_net_lines({}, False, {"fenced": True}) == ""
    go, _, _ = p44
    run = go(P44_LOCAL, hosts=MISSING, offline=MISSING)
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run", [m["text"] for m in run.chat]
    card = p32_card(run)
    assert "Internet access" not in card and "offline command" not in card and "couldn't be checked" not in card, card

# ---- P44 (D449) T4: P35 compares the offline dry run's file changes with expect unless the plan says it can't ----------------
P44_OTHER = P44_FETCH.replace("'title.txt'", "'other.txt' if src == '--offline' else 'title.txt'")      # offline: another file


def test_p44_offline_mismatch_goes_back_to_the_builder(p44):
    """A guard that P35 keeps comparing the offline command's changes with expect: passes before the amendment too."""
    go, _, _ = p44
    run = go(P44_OTHER)
    assert run._ask_real_run({}) is True
    w = run.workflows[0]
    assert w["failure"][0] == "dry_run" and "not what it said it would do" in w["failure"][1], w.get("failure")
    assert run.turn == "adaptation" and not [m for m in run.chat if m.get("real_run")]


def test_p44_same_files_false_skips_expect_with_the_card_line(p44):
    go, real, _ = p44
    run = go(P44_OTHER, offline={"command": [sys.executable, "fetch.py", str(real), "--offline"], "same_files": False})
    assert run._ask_real_run({}) is True and run.paused["kind"] == "real_run", [m["text"] for m in run.chat]
    assert "expect_mismatch" not in run.real_runs_dry["W-1"] and run.workflows[0].get("failure") is None
    assert "\nFile changes couldn't be checked first." in p32_card(run)

# ---- P44 (D449) T5: a failed dry run never makes built work "not built" (P30 amended); run 458e's shape, made-up data ---------
def test_p44_a_dry_run_failure_keeps_the_builders_built_items(p44):
    go, real, _ = p44
    run = go(P44_FETCH.replace("body = ", "sys.exit(1) if src == '--offline' else None\nbody = "))      # offline: exit 1
    crit = run.goal["done_when"]
    run.goal["item_checks"] = {crit[0]: {"type": "file-exists", "target": "fetch.py", "expect": True},
                               crit[1]: {"type": "file-exists", "target": "test_fetch.py", "expect": True},
                               crit[2]: {"type": "real-run"}}
    run.workflows[0]["item_status"] = {crit[0]: {"status": "built", "reason": ""}, crit[1]: {"status": "built", "reason": ""}}
    assert run._ask_real_run({}) is True
    w = run.workflows[0]
    assert w["status"] == "failed" and w["failure"][0] == "dry_run", w.get("failure")
    assert run._open_items() == [], run._open_items()      # never "(not built: no workflow built it)"
    assert run._item_states()[crit[0]]["wid"] == "W-1"
    assert any("done-when item 3" in x for x in run._real_run_pending()), "the real run's item stays open"
    reg, refused, _ = run._register([{**sort_proposals(str(real), fix=True)[0], "real_run": None, "revises": "W-1"}])
    assert len(reg) == 1 and not refused, refused
    w2 = reg[0]      # a later done revision's own statuses win
    w2["status"] = "done"
    w2["item_status"] = {crit[0]: {"status": "not_built", "reason": "x"}}
    assert run._item_states()[crit[0]]["status"] == "not_built" and run._item_states()[crit[0]]["wid"] == w2["id"]

# ---- P44 (D449) T6: a real run is never run again without its own Run press (a pin; no code change) ------------------------
def test_p44_a_failed_real_run_is_never_run_again_without_its_own_code(j2ft, p44, p44_reg, monkeypatch):
    """FR-10: an approved real run that fails is not run again by itself: the same workflow is never asked again, and a
    replacement gets its own card and code and runs only after its own RUN <code>. That Decide for me's exact RUN <code> never
    runs one is pinned by P31 (test_p31_a_reply_that_is_not_the_code_asks_again_and_keeps_the_run_open); not repeated here.
    Passes before and after P44: _ask_real_run skips a workflow already asked (real_runs_asked)."""
    go, real, _ = p44
    calls, orig = [], j2ft.real_run
    monkeypatch.setattr(j2ft, "real_run", lambda out, rr, t: calls.append(rr.get("fence") is True) or orig(out, rr, t))
    unfenced = lambda: sum(1 for f in calls if not f)
    run = go(P44_FETCH.replace("body = ", "sys.exit(1) if src != '--offline' else None\nbody = "))      # real: exit 1
    assert run._ask_real_run({}) is True and run.paused["kind"] == "real_run"
    p31_answer(run, f"RUN {run.real_runs_asked['W-1']}")
    r = p31_receipts(run)[-1]
    assert r["approved"] and r["ran"] and r["exit"] == 1 and unfenced() == 1, (r, calls)
    assert run._ask_real_run({}) is False and unfenced() == 1
    assert (run.paused or {}).get("kind") != "real_run"
    reg, refused, _ = run._register([{**p44_reg.proposal(run)[0], "revises": "W-1", "parts": ["fix"]}])      # a replacement
    # that keeps the real run; W-1 is done (only its real run failed), so rewriting it is priced as a fix
    assert len(reg) == 1 and not refused, refused
    w2 = reg[0]
    w2["status"] = "done"
    assert run._ask_real_run({}) is True and run.paused["kind"] == "real_run" and unfenced() == 1
    assert run.real_runs_asked[w2["id"]] != run.real_runs_asked["W-1"]
    assert any(m.get("real_run") == w2["id"] for m in run.chat), "the replacement gets its own card"
    p31_answer(run, f"RUN {run.real_runs_asked[w2['id']]}")
    assert unfenced() == 2

# ---- P44 (D449) T7: the proxy names join the fixed guardrail list (D446 amended, P41 amended) -------------------------------
@pytest.mark.parametrize("name", ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy",
                                  "no_proxy"])
@pytest.mark.parametrize("hosts", [True, False])
def test_p44_proxy_settings_are_refused_with_or_without_hosts(p44_reg, name, hosts):
    """srt's own proxy can't be overridden by a plan: a proxy name is refused as a setting, in either case, with hosts or not."""
    kw = {} if hosts else {"hosts": MISSING, "offline": MISSING}
    run, reg, refused = p44_reg.register(settings={name: "http://made-up.invalid:3128"}, **kw)
    assert not reg and len(refused) == 1 and run.rejections[-1]["key"] == ["real_run_env"], refused
    assert f"real_run may not set {name}" in refused[0] and "where it connects (a fixed guardrail list)" in refused[0], refused

# ---- P44 (D449) T8: the planner and the builder are told how hosts, the offline command and the read-only first call work ------
def p44_builder_prompt(j2ft, tmp_path, runner):
    """The tools builder's first prompt for a made-up workflow (as P41's test captures it), with the form's runner or none."""
    run = j2ft.J2Run(run_dir=tmp_path / "runs" / f"j2-20261125-0903{'01' if runner else '02'}-5e12")
    run._apply_output(FT)
    if not runner:
        run.out = {**run.out, "test_runner": None}
    run.goal, run.budget = {"statement": "fetch", "done_when": ["fetch.py saves the page title"]}, 100
    os.makedirs(run._out_dir(), exist_ok=True)
    w = {"id": "W-1", "name": "fetcher", "purpose": "fetch", "outputs": [f"{FT}/fetch.py"], "status": "running", "calls_used": 0,
         "retries_used": 0, "cost": 10, "cycle": 1, "section": "W-1", "covers": [1],
         "atoms": [{"id": "W-1.a1", "goal": "fetch", "expected_output": [],
                    "verification": [{"text": "fetch.py exists", "type": "file-exists", "target": "fetch.py", "expect": True}]}]}
    run.workflows = [w]
    j2ft.add_workflow_agent("W-1")
    prompts = []

    def call(fn, fmt, prompt, mock, **kw):
        prompts.append(prompt)
        (Path(run._out_dir()) / "fetch.py").write_text("print('made-up')\n")
        return {"say": "@Coordination built", "human_output": "I built it.", "atom_human_output": "The fetcher."}
    run.call = call
    run._run_tools(w, {"id": "W-1", "name": "fetcher", "outputs": w["outputs"]}, 3)
    assert prompts
    return prompts[0]


def test_p44_rules_join_with_tools_and_runner(j2ft, tmp_path, monkeypatch):
    """A hint, not enforced: code checks the hosts and the offline command at registration and grants hosts only after Run."""
    rule = j2ft.REAL_RUN_NET_RULE
    for x in ('"hosts"', '"reaches"', '"offline"', '"same_files"', "made-up data", "read-only call", "*.example.com only if",
              ":port", "80 characters", "asked once", "Only code and the Run card grant internet access", "never tell anyone",
              "HTTP_PROXY"):
        assert x in rule, x
    monkeypatch.setenv("J2_AGENT_TOOLS", "1")
    run = j2ft.J2Run(run_dir=tmp_path / "runs" / "j2-20261125-090300-5e12")
    run._apply_output(FT)
    assert run.out.get("test_runner") and j2ft.llm.tools_on()
    assert run.ATOM_RULES.endswith(j2ft.REAL_RUN_ENV_RULE + rule)
    monkeypatch.setenv("J2_AGENT_TOOLS", "0")
    run._apply_output(FT)
    assert rule not in run.ATOM_RULES
    hint = j2ft.SCRIPT_NET_RULE
    for x in ("read-only check", "a bad key or missing access fails", "--mock", "--dry-run", "made-up data", "fake local server",
              "never promise it"):
        assert x in hint, x
    monkeypatch.setenv("J2_AGENT_TOOLS", "1")
    told = p44_builder_prompt(j2ft, tmp_path, runner=True)
    assert j2ft.SCRIPT_ENV_RULE + hint in told, told[:2000]
    assert hint not in p44_builder_prompt(j2ft, tmp_path, runner=False)


# ---- P44 (D449): the deliverables planner's replies that were not JSON are kept in deliverables.json -----------------------
NOT_JSON = "Here is the plan: (not JSON)"      # made-up text, no model call


def test_p44_the_deliverables_planners_unreadable_replies_are_kept(j2, make_run, monkeypatch):
    """The plan and its one revision both come back as text: the run stops as before, and both replies are kept."""
    real = j2.j2_realization.deliverable_mocks
    monkeypatch.setattr(j2.j2_realization, "deliverable_mocks",
                        lambda goal, names: {**real(goal, names), "plan": lambda rnd: NOT_JSON, "revise": lambda rnd: NOT_JSON})
    run = make_run()
    say(run, BREW_LAB)
    assert run.outcome == "Stopped: the plan chose nothing J2 can build.", run.outcome
    saved = json.loads((Path(run.dir) / "deliverables.json").read_text())
    assert [(u["who"], u["raw"], u["chars"]) for u in saved["unparsed"]] == [("adaptation", NOT_JSON, len(NOT_JSON))] * 2, saved
    assert "trail" not in saved
    note = "The planner's reply could not be read as JSON (2 times); kept in deliverables.json under unparsed."
    assert [m for m in run.chat if m.get("text") == note and m["who"] == "system"], run.chat[-5:]


def test_p44_a_json_plan_keeps_no_unparsed_key(j2, make_run):
    run = make_run()
    say(run, BREW_LAB)
    saved = json.loads((Path(run.dir) / "deliverables.json").read_text())
    assert "unparsed" not in saved and "trail" not in saved and saved["deliverables"]
    assert not [m for m in run.chat if "could not be read as JSON" in str(m.get("text"))]


# ---- P45 (D452): the programs the engine builds and runs ---------------------------------------------------------------------
# Modelled on three Pulse runs of the beta: j2-20261123-103238-3429 and j2-20261124-113042-87be (an agent stage with a document's
# charter, C2 "the test '' is not a file in the folder", a list of files read as one name, "unknown check test-passed") and
# j2-20261125-045739-52c5 (Decide for me confirmed the folder of the install and the live read; an install card with no packages;
# C2 never rerun after a declined install). No model call, no network.
P45_PRINTS = ("import json, os, sys\nprint('read 3 threads')\nsys.stderr.write('1 warning\\n')\n"
              "json.dump({'threads': 3}, open(os.path.join(sys.argv[1], 'out.json'), 'w'))\n"
              "open(os.path.join(sys.argv[1], 'mail.txt'), 'w').write('one two')\n"
              "old = os.path.join(sys.argv[1], 'old.txt')\nos.path.exists(old) and os.remove(old)\n")
P45_FILES = {"tests/test_x.py": "print('OK')\n", "pulse/run.py": "X = 1\n", "README.md": "# Pulse\n"}
P45_DOC_CHARTER = {"statement": "An agent for Pulse", "site_name": "Pulse", "business_type": FT, "done_when": ["it runs"]}


def p45_check(kind, target):
    return {"text": f"{kind} {target}", "type": kind, "target": target, "expect": True}


def p45_made(env_run, files, checks, goal=None):
    """env_run's run with these files (folders made) and these checks on its one atom; goal: its charter."""
    made, real = env_run
    run, w = made({})
    for name, text in files.items():
        path = Path(run._out_dir(), name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    w["atoms"][0]["verification"] = checks
    if goal:
        run.goal = dict(goal)
    return run, w, real


def test_p45_an_agent_stage_gets_its_own_intake_and_charter_never_a_documents(j2env, tmp_path):
    run = j2env.J2Run(run_dir=tmp_path / "runs" / "j2-20261124-113042-87be")
    run._apply_output("prd")
    run.request = "Build a script for Pulse, with a PRD first."
    run.post("user", run.request)
    base = {"statement": "A PRD for Pulse", "product_name": "Pulse", "site_name": "Pulse", "business_type": "prd",
            "done_when": ["The Problem section is written for Pulse"]}
    run.goal, run.docset = base, ["prd"]
    run.stages, run.stage_i, run.stage_archive = ["prd", FT], 1, [{"stage": "prd", "goal": base, "audits": [], "sections": {}}]
    run._begin_stage(FT, base)
    assert run.folder and run.goal is None and run.turn == "identity" and run.handoff.get("kind") == "intake"
    assert p42_system(run)[-1] == "The documents are done. Now the script, built from them."
    assert not any("written from the" in x for x in p42_system(run))      # 87be: "Next: the PULSE_AGENT, written from the HLD's agent_output."
    run._turn_identity(run.handoff)
    assert run.goal["files"] == ["main.py", "test_main.py", "README.md"] and run.goal["test"] == "test_main.py"
    assert run.goal["statement"] != f"An {FT.upper()} for Pulse"      # stage_goal's document charter: no files, no test


def test_p45_the_browser_check_is_a_pages_and_a_folder_is_never_called_the_site(j2env, env_run, tmp_path):
    made, _ = env_run
    run, _ = made({})
    audit = {"version": 1, "output": FT, "results": [], "rubric": [], "conditions": [], "mechanical": {}}
    assert "the browser check didn't run" not in run._open_list(audit, [])      # 52c5: listed as failing, for a folder of Python
    page = j2env.J2Run(run_dir=tmp_path / "runs" / "j2-20261125-000000-page")
    page._apply_output("website")
    page.goal, page.sites = {"done_when": []}, ["v1"]
    assert "the browser check didn't run" in page._open_list({**audit, "output": "website"}, [])
    assert run._thing() == run.out["noun"] != "site" and page._thing() == "site"
    src = Path(j2env.__file__).read_text(encoding="utf-8")
    assert "the {self._thing()} isn't workable, so done-when can't hold" in src and "the site isn't workable" not in src.split("class J2Run", 1)[1]


@pytest.mark.parametrize("kind, question, about", [
    ("question", "Is /Users/x/Documents/Pulse the folder where the agent should be written and where the install and the read "
                 "of your mail should run?", "installing packages"),      # 52c5, msg 39: answered "Yes, that folder is right"
    ("info", "May the team install what the script needs?", "installing packages"),
    ("question", "Should the live read of the mailboxes go ahead now?", "a real run"),
    ("conflict", "Do you want the real run kept in the plan?", "a real run"),
    ("question", "Which folder should the script run in?", "the folder a real run uses")])
def test_p45_decide_for_me_never_answers_about_a_real_run_an_install_or_its_folder(env_run, kind, question, about):
    made, _ = env_run
    run, _ = made({"s.py": P42_GOOD})
    run.auto = True
    run._ask_user("One thing to confirm.", [{"question": question, "options": ["Yes", "No"]}], kind, handoff={"kind": "x"})
    n = len(run.chat)
    assert run._auto_pick() is None and run.paused["kind"] == kind
    assert p42_system(run)[-1] == f"Decide for me did not answer this question: it is about {about}. It waits for you."
    run._auto_go()
    assert run._auto_pick() is None and len(run.chat) == n + 1 and not any(m.get("auto") for m in run.chat)      # said once, nothing answered


def test_p45_decide_for_me_leaves_a_pending_real_run_open_drops_no_item_and_still_answers_ordinary_questions(j2env, env_run):
    made, real = env_run
    run, w = made({"s.py": P42_GOOD})
    run.auto = True
    item = run.goal["done_when"][0]
    assert {"limit", "real_run", "send_confirm"} <= j2env.AUTO_ASK
    run._ask_user("A fact.", [{"question": "Did it happen?", "kind": "decision", "item": 1, "options": ["Yes", "No"]}], "fact")
    assert run._auto_pick() is None      # tagged with the item its real run decides
    run._ask_user("A choice.", [{"question": "Keep going or leave something out?", "options": ["Keep going", "Leave it out"]}],
                  "conflict", handoff={"kind": "x", "drop_texts": [item]})
    assert run._auto_pick() is None      # its leave-out option names a real-run item
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run"
    run._auto_go()
    assert run.paused["kind"] == "real_run" and not p42_receipts(run) and run.goal["done_when"] == [item] and not run.real_runs_done
    assert not (real / "out.txt").exists()
    run._ask_user("One choice is up to you.", [{"question": "Which heading colour?", "options": ["Blue", "Green"]}], "question",
                  handoff={"kind": "x"})
    assert run._auto_pick()[:2] == ("Option 1", "Blue")


def p45_sha(data):
    return hashlib.sha256(data).hexdigest()


def p45_run_it(env_run, script, result=None):
    """env_run's run with this script, approved with its code: (run, workflow, real folder, the receipt, the record or None)."""
    made, real = env_run
    run, w = made({"s.py": script})
    if result is not None:
        w["real_run"]["result"] = result
    assert run._ask_real_run({}) and run.paused["kind"] == "real_run"
    p42_reply(run, f"RUN {run.real_runs_asked['W-1']}")
    r = p42_receipts(run)[-1]
    return run, w, real, r, json.loads(Path(run.dir, r["run_output"]).read_text()) if r.get("id") else None


def test_p45_an_approved_real_run_leaves_a_run_output_record_as_the_contract_says(j2env, env_run):
    _, real = env_run
    (real / "old.txt").write_text("gone soon")
    (real / "untouched.txt").write_text("same")
    lim = j2env.OWN_RUNS["run_output"]["limits"]
    assert lim == {"stdout_lines": 200, "stderr_lines": 50, "tail_bytes": 65536, "max_files": 500, "text_cap_bytes": 65536}
    run, w, real, r, rec = p45_run_it(env_run, P45_PRINTS, result="out.json")
    assert r["approved"] and r["ran"] and r["exit"] == 0 and r["id"] == "rr-W-1-1" and r["run_output"] == "run_output/rr-W-1-1.json"
    assert r["output"] == "read 3 threads\n1 warning\n"      # as before P45: the last 1,500 characters of stdout and stderr
    assert r["run_output_counts"] == {"created": 1, "changed": 1, "deleted": 1, "stdout_lines": 1, "stderr_lines": 1}
    # the real run's own file changes, on the real folder, in the format of dry_run.created / changed / deleted (relative paths, sorted)
    assert (r["created"], r["changed"], r["deleted"]) == (["out.json"], ["mail.txt"], ["old.txt"])
    assert all(isinstance(x, str) for k in ("created", "changed", "deleted") for x in r["dry_run"].get(k) or [])      # no sandbox here: no dry run
    assert r["files_truncated"] is False and r["result"] == "out.json" and "capture" not in r and "capture" not in w["real_run"]
    assert r["stdout"].strip() == "read 3 threads" and r["stderr"].strip() == "1 warning"      # P42's tails stay in the receipt
    assert list(rec) == ["schema", "receipt", "workflow", "command", "folder", "approved", "started_at", "ended_at", "exit", "main_result",
                         "files", "files_truncated", "stdout", "stderr", "limits"] and rec["files_truncated"] is False
    assert rec["schema"] == "run-output/1" and rec["receipt"] == "rr-W-1-1" and rec["workflow"] == "W-1" and rec["folder"] == str(real)
    assert rec["command"] == ["python3", "s.py", str(real)] and rec["approved"] is True and rec["exit"] == 0 and rec["limits"] == lim
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", rec["started_at"]) and rec["started_at"] <= rec["ended_at"]
    data = (real / "out.json").read_bytes()
    assert rec["main_result"] == {"path": "out.json", "exists": True, "size": len(data), "sha256": p45_sha(data), "text": data.decode()}
    assert rec["files"] == {"created": [{"path": "out.json", "size": len(data), "sha256": p45_sha(data)}],
                            "changed": [{"path": "mail.txt", "before": {"size": 3, "sha256": p45_sha(b"one")},
                                         "after": {"size": 7, "sha256": p45_sha(b"one two")}}],
                            "deleted": [{"path": "old.txt", "size": 9, "sha256": p45_sha(b"gone soon")}]}      # no contents here
    assert rec["stdout"] == {"tail": "read 3 threads", "lines_total": 1, "truncated": False}
    assert rec["stderr"] == {"tail": "1 warning", "lines_total": 1, "truncated": False}
    rows = [x for x in j2env.j2_artifacts.rows(run.dir) if x["kind"] == "run_output"]
    assert len(rows) == 1 and rows[0]["file"] == "run_output/rr-W-1-1.json" and rows[0]["type"] == "run_output" and rows[0]["name"] == "Run output"
    assert rows[0]["form"] == "data" and rows[0]["deliverable"] is False
    assert "run_output" not in {t["name"] for t in j2env.j2_artifacts.load_types()["types"]}      # never a type an agent can choose
    from sutra_app.library.wire import ArtifactsDoc
    assert [x.kind for x in ArtifactsDoc.model_validate({"schema": "artifacts/1", "rows": j2env.j2_artifacts.rows(run.dir)}).rows].count("run_output") == 1


def test_p45_the_run_output_limits_hold_and_the_main_result_is_null_missing_or_without_text(j2env, env_run):
    lim = j2env.OWN_RUNS["run_output"]["limits"]
    big = "x" * (lim["text_cap_bytes"] + 1)
    loud = ("import os, sys\nfor i in range(300):\n    print('line', i)\n    sys.stderr.write('err %d\\n' % i)\n"
            f"open(os.path.join(sys.argv[1], 'big.txt'), 'w').write({big!r})\n")
    *_, rec = p45_run_it(env_run, loud, result="big.txt")
    assert rec["stdout"]["lines_total"] == 300 and rec["stdout"]["truncated"] and rec["stdout"]["tail"].splitlines() == [f"line {i}" for i in range(100, 300)]
    assert rec["stderr"]["lines_total"] == 300 and rec["stderr"]["truncated"] and rec["stderr"]["tail"].splitlines() == [f"err {i}" for i in range(250, 300)]
    assert rec["main_result"]["exists"] and rec["main_result"]["size"] == len(big) and "text" not in rec["main_result"]
    run, _, _, r, rec = p45_run_it(env_run, P45_PRINTS)      # the plan declares none, and the type's entry_file is a pattern
    assert rec["main_result"] is None and r["result"] == run.out["entry_file"] == f"{FT}/*"
    assert p45_run_it(env_run, P45_PRINTS, result="never.json")[-1]["main_result"] == {"path": "never.json", "exists": False}


def test_p45_without_a_declared_result_the_types_entry_file_is_the_result_when_it_names_one_file(j2env, env_run):
    made, real = env_run
    run, w = made({"s.py": P45_PRINTS})
    run.out = {**run.out, "entry_file": f"{FT}/s.py"}
    run._ask_real_run({})
    p42_reply(run, f"RUN {run.real_runs_asked['W-1']}")
    r = p42_receipts(run)[-1]
    main = json.loads(Path(run.dir, r["run_output"]).read_text())["main_result"]
    assert r["result"] == f"{FT}/s.py" and main["path"] == f"{FT}/s.py" and main["exists"] and main["text"] == P45_PRINTS


def test_p45_more_files_than_max_files_stops_the_lists_and_says_files_truncated(j2env, env_run, monkeypatch):
    monkeypatch.setitem(j2env.OWN_RUNS["run_output"]["limits"], "max_files", 2)
    many = "import os, sys\nfor i in range(5):\n    open(os.path.join(sys.argv[1], 'n%d.txt' % i), 'w').write('x')\n"
    _, _, _, r, rec = p45_run_it(env_run, many)
    assert r["files_truncated"] is True and rec["files_truncated"] is True and r["created"] == ["n0.txt", "n1.txt"]
    assert [f["path"] for f in rec["files"]["created"]] == ["n0.txt", "n1.txt"] and r["run_output_counts"]["created"] == 5


def test_p45_a_run_that_was_not_approved_leaves_no_record_and_the_plans_result_is_checked_by_code(j2env, env_run):
    made, _ = env_run
    run, w = made({"s.py": P45_PRINTS})
    run._ask_real_run({})
    p42_reply(run, "Don't run")
    r = p42_receipts(run)[-1]
    assert not {"id", "run_output", "run_output_counts", "created", "changed", "deleted", "files_truncated"} & set(r)
    assert not Path(run.dir, "run_output").exists() and "capture" not in w["real_run"]
    for bad in ("/etc/passwd", "../out.json", "a/../../x", "", 7, "out/"):
        assert j2env.real_run_result_problems({"result": bad}), bad
    assert j2env.real_run_result_problems({"result": "out/report.json"}) == [] and j2env.real_run_result_problems({}) == []
    assert j2env.REAL_RUN_RESULT_RULE in run.ATOM_RULES and '"result"' in j2env.REAL_RUN_RESULT_RULE      # prompt-changing (D249)


@pytest.mark.parametrize("target", ["tests/test_x.py", f"{FT}/tests/test_x.py", ["tests/test_x.py"]])
def test_p45_c2_finds_the_test_the_builder_wrote_when_the_charter_names_none(env_run, target):
    run, w, _ = p45_made(env_run, P45_FILES, [p45_check("test-passed", target)], P45_DOC_CHARTER)
    c = {"id": "C2", "check": "test-passed"}
    met, why = run._folder_condition(c)
    assert met and "tests/test_x.py exited 0" in why and "from_charter" not in c


def test_p45_c2_with_no_test_anywhere_stays_unmet_and_the_charters_test_comes_first(env_run):
    run, w, _ = p45_made(env_run, P45_FILES, [p45_check("file-exists", "README.md")], P45_DOC_CHARTER)
    c = {"id": "C2", "check": "test-passed"}
    assert run._folder_condition(c) == (False, "code reran the test itself, on a copy of the folder, not the builder's own run: "
                                               "the test '' is not a file in the folder") and c["from_charter"] is True      # P29 (D431) holds
    run, w, _ = p45_made(env_run, P45_FILES, [p45_check("test-passed", "missing.py")], {**P45_DOC_CHARTER, "test": "tests/test_x.py"})
    assert run._folder_condition({"id": "C2", "check": "test-passed"})[0]


def test_p45_list_targets_are_checked_item_by_item_and_a_recheck_keeps_its_folder(j2env, env_run):
    run, w, _ = p45_made(env_run, P45_FILES, [p45_check("file-exists", ["pulse/run.py", "tests/test_x.py", "README.md"]),
                                              p45_check("test-passed", ["tests/test_x.py"])], P45_DOC_CHARTER)
    assert run._run_checks(w, 1, "", folder=run._out_dir()) == []      # 87be: a list was read as one file name, and failed
    w["atoms"][0]["verification"] = [p45_check("file-exists", ["pulse/run.py", "gone.py"])]
    failed = run._run_checks(w, 1, "", folder=run._out_dir())
    assert len(failed) == 1 and "gone.py" in failed[0]["evidence"] and "pulse/run.py" not in failed[0]["evidence"]
    w["atoms"][0]["verification"] = [p45_check("file-exists", f"{FT}/pulse/run.py"), p45_check("test-passed", f"{FT}/tests/test_x.py")]
    assert run._run_checks(w, 1, "", folder=run._out_dir()) == []      # 3429: the run-relative form is read in the builder's folder
    w["atoms"][0]["verification"] = [p45_check("test-passed", "tests/test_x.py"), p45_check("inside-folder", ".")]
    assert run._run_checks(w, j2env.MAX_CHECK_ATTEMPTS, "", atoms=w["atoms"], recheck="check corrected by Adaptation") == []
    assert not any("unknown check" in r.get("evidence", "") for r in w["atoms"][0]["results"])      # 87be: "unknown check test-passed"


def test_p45_one_path_form_a_mix_is_refused_and_the_folders_name_in_front_is_taken_off(j2env, env_run):
    mix = {"name": "build", "atoms": [{"verification": [p45_check("file-exists", f"{FT}/pulse/run.py"), p45_check("test-passed", "tests/test_x.py")]}]}
    probs, n = j2env.path_form_problems(mix, FT)
    assert len(probs) == 1 and "two forms" in probs[0] and n == 0 and mix["atoms"][0]["verification"][0]["target"] == f"{FT}/pulse/run.py"
    front = {"name": "build", "atoms": [{"verification": [p45_check("file-exists", [f"{FT}/pulse/run.py", f"{FT}/README.md"]),
                                                             p45_check("test-passed", f"{FT}/tests/test_x.py")],
                                         "expected_output": [{"text": "the test", "kind": "file", "target": f"{FT}/tests/test_x.py"}]}]}
    probs, n = j2env.path_form_problems(front, FT)
    a = front["atoms"][0]
    assert (probs, n) == ([], 4) and a["verification"][0]["target"] == ["pulse/run.py", "README.md"]
    assert a["verification"][1]["target"] == "tests/test_x.py" and a["expected_output"][0]["target"] == "tests/test_x.py"
    assert j2env.path_form_problems({"atoms": [{"verification": [p45_check("file-exists", "pulse/run.py"),
                                                                p45_check("file-exists", f"./{FT}/x.py")]}]}, FT) == ([], 0)
    assert j2env.path_form_problems({"atoms": [{"verification": [p45_check("file-exists", "../x.py")]}]}, FT)[0]
    # the validator refuses the mix when a workflow is registered (the atom's own fields are complete)
    run, w, _ = p45_made(env_run, P45_FILES, mix["atoms"][0]["verification"], P45_DOC_CHARTER)
    assert j2env.atom_missing(w) or any("two forms" in p for p in run._atom_problems(w))


@pytest.mark.parametrize("text", ["", "\n", "# nothing to install\n\n"])
def test_p45_a_requirements_txt_with_no_package_plans_no_environment_and_asks_nothing(j2env, env_run, text):
    files = {"helper.py": "VALUE = 1\n", "test_ok.py": "import unittest\nimport helper\nassert helper.VALUE == 1\n", "requirements.txt": text}
    run, w, _ = p45_made(env_run, files, [p45_check("test-passed", "test_ok.py")])
    assert j2env.j2_runenv.plan(run._out_dir()) is None      # 52c5: "Packages to install, from PyPI only: " and nothing after it
    n = len(run.chat)
    assert run._env_ask(w, 1, run._out_dir()) is False and not run.paused and len(run.chat) == n
    assert run._run_checks(w, 1, "", folder=run._out_dir()) == [] and w["atoms"][0]["results"][0]["pass"] is True


def test_p45_packages_not_installed_never_block_a_test_that_needs_only_the_standard_library(j2env, env_run):
    files = {"helper.py": "VALUE = 1\n", "test_ok.py": "import unittest\nimport helper\nassert helper.VALUE == 1\nprint('OK')\n",
             "test_needs.py": "import pulsedep\n", "requirements.txt": "pulsedep==9.9.9\n"}      # a hash no other test installs
    run, w, _ = p45_made(env_run, files, [p45_check("test-passed", "test_ok.py")], {"statement": "x", "done_when": ["it runs"], "test": "test_ok.py"})
    runenv, out = j2env.j2_runenv, run._out_dir()
    plan = runenv.plan(out)
    assert plan and not plan["ready"] and plan["packages"] == ["pulsedep==9.9.9"]
    assert runenv.beyond_stdlib(os.path.join(out, "test_ok.py"), out) == [] and runenv.beyond_stdlib(os.path.join(out, "test_needs.py"), out) == ["pulsedep"]
    assert run._run_checks(w, 1, "", folder=out) == [] and "exited 0" in w["atoms"][0]["results"][0]["evidence"]
    met, why = run._folder_condition({"id": "C2", "check": "test-passed"})      # 52c5: "the test was not rerun", in every audit
    assert met and "exited 0" in why
    w["atoms"][0]["verification"] = [p45_check("test-passed", "test_needs.py")]
    run._run_checks(w, 1, "", folder=out)
    res = w["atoms"][0]["results"][0]
    assert res["pass"] is None and res["evidence"].startswith("the test was not rerun: its packages are not installed")


def test_p45_the_data_file_is_j2s_own_and_names_the_vocabulary_and_the_sizes():
    """engine/j2_own_runs.json is a byte copy of J2's (prototypes/j2). Skipped where the prototype is not checked out."""
    mine = Path(__file__).resolve().parents[2] / "sutra_app" / "engine" / "j2_own_runs.json"
    data = json.loads(mine.read_text(encoding="utf-8"))
    assert [set(x) for x in data["requester_only"]] == [{"about", "pattern"}] * 3 and all(re.compile(x["pattern"]) for x in data["requester_only"])
    assert set(data["run_output"]) == {"folder", "name", "kind", "label", "tag", "color", "limits"} and data["run_output"]["kind"] == "run_output"
    theirs = Path(__file__).resolve().parents[3] / "prototypes" / "j2" / "j2_own_runs.json"
    if not theirs.is_file():
        pytest.skip("prototypes/j2 is not here")
    assert theirs.read_bytes() == mine.read_bytes()
