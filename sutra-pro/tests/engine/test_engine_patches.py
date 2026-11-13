"""The patches of the vendored J2 (work package E1, engine design 3.4): P2 role-file folder, P3 explicit run folder and id,
P4 non-blocking user_says and apply_override, P5 explicit-path memory and saved-run functions, P7 tagged model calls,
P8 hooks, P9 the system addendum, P14 `single` with no type, P16 Decide for me's settings file, P17 the local type store and
P18 host type registration (sync 5). J2 runs in mock mode with its Chrome checks faked (as J2's own `--fast` flow does), so a
whole Brew Lab run takes about a tenth of a second. P1 (imports) and P10 (the library lock) are in test_engine_vendor.py and
test_engine_library_lock.py, P11 (rehydrate) in test_engine_rehydrate.py."""
import contextlib
import hashlib
import importlib
import itertools
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import pytest

ENGINE = "sutra_app.engine"
J2_MODULES = ("j2", "j2_agent", "j2_agent_models", "j2_agent_views", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change",
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
def hooked_run(j2, make_run, mock_mode, texts=(BREW_LAB,), **kw):
    mock_mode.configure(mock=True, base_tag=base_tag())
    rec = recorder()
    run = make_run(hooks=rec, **kw)
    rec.run = run
    for text in texts:
        say(run, text)
    return run, rec


def test_p8_a_hooked_run_pairs_every_turn_start_with_its_finish(j2, make_run, mock_mode):
    run, rec = hooked_run(j2, make_run, mock_mode)
    names = [c[0] for c in rec.calls]
    assert names[:4] == ["message_posted", "run_status", "record_saved", "turn_started"] and names[-1] == "run_status"
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
    entry = jt.create("brew_notes", "Brew notes", SECTIONS)
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
            jt.create("brew_notes", "Brew notes", SECTIONS)
    finally:
        oslayer.unlock(fd)
        os.close(fd)
    assert not (store / "types.local.json").exists()
    assert jt.create("brew_notes", "Brew notes", SECTIONS)["name"] == "brew_notes", "free again"


def test_p17_two_threads_creating_different_types_lose_neither(jt, tmp_path):
    errors, names = [], ["alpha_notes", "beta_notes", "gamma_notes", "delta_notes"]

    def make(name):
        try:
            jt.create(name, name.replace("_", " ").title(), SECTIONS)
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
        jt.create("host_doc", "Host doc", SECTIONS)


def test_p18_register_clears_the_cache_so_the_type_shows_at_once(jt, tmp_path):
    before = jt.names()
    jt.register(host_entry(tmp_path, jt))
    assert set(jt.names()) == set(before) | {"host_doc"}
