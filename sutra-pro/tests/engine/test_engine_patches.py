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
import sys
import threading
import time
from pathlib import Path

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

def tools_call(j2, run, said=None, extra=None, temps=()):
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
          "why": "The brief asks to run the script on the Requester's own folder.", "checks": [3]}
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
    out = finish(run, {MORNING[1]: {"status": "blocked", "reason": "no channel token given"}})
    assert out.startswith("Done with open items: not every done-when item is built."), out
    assert f"done-when item 2: {MORNING[1]} (blocked: no channel token given)" in out
    run.sites = ["## Users"]
    assert f"{MORNING[1]} (blocked: no channel token given)" in run._ship_outcome("on request")
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
