"""Continuing a finished run (work package E1, patch P11, engine design 4.8, S1-contracts-12): a follow-up after Done is a new
run whose `J2Run` is brought back from the old folder by `rehydrate`, or a fresh run when the old one cannot be continued.
J2 runs in mock mode with its Chrome checks faked (as J2's own `--fast` flow does)."""
import contextlib
import hashlib
import importlib
import itertools
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

ENGINE = "sutra_app.engine"
J2_MODULES = ("j2", "j2_agent", "j2_artifact_models", "j2_artifacts", "j2_board", "j2_change", "j2_check", "j2_map",
              "j2_realization", "j2_rules", "j2_schema", "j2_send", "j2_story", "j2_template_lib", "rehydrate")
BREW_LAB = ("A one-page website for Brew Lab, a small specialty coffee shop in Indiranagar, Bengaluru. Visitors should "
            "see the menu with prices, the opening hours, and where to find us, and be able to pre-order a coffee for "
            "pickup. It should feel warm and modern and work well on a phone. Include a section about our beans and the "
            "farms they come from, and a simple loyalty-card explainer (buy 9, get the 10th free).")
VAGUE = ["a website for my cafe",
         "It's called Little Fig, in Koramangala, Bengaluru. Visitors should see our menu with prices, opening hours and "
         "where to find us. Cozy and simple, and it must work on phones.",
         "Option 2: skip the stories, keep the reserve for fixes."]
CHANGE = "Add a section for visiting hours"
HOST_SENTINELS = {"task.json": '{"host": "task"}', "settings.json": '{"host": "settings"}', "events.jsonl": '{"t": "host"}\n',
                  "inbox.jsonl": '{"n": 1}\n', "trace.jsonl": '{"seq": 1}\n'}


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
        for key, value in {"STUDIO_MOCK": "1", "J2_MEMORY": "0", "J2_REALIZATION": "0", "J2_MEMORY_FILE": base / "lessons.jsonl",
                           "J2_PLAYBOOK_FILE": base / "playbooks.jsonl", "J2_RUNS_DIR": base / "runs",
                           "J2_LIBRARY_DIR": base / "library"}.items():
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


@pytest.fixture(scope="module")
def j2(tmp_path_factory):
    with fresh_j2(tmp_path_factory.mktemp("j2-env")) as mod:
        yield mod


@pytest.fixture(autouse=True)
def mock_mode(llm_reset):
    llm_reset.configure(mock=True)
    return llm_reset


@pytest.fixture
def new_run(j2, tmp_path):
    """A fresh J2Run in a new run folder that holds the files the host makes (task.json and friends)."""
    counter = itertools.count(1)

    def make(host_files=True, **kw):
        folder = tmp_path / "runs" / f"j2-20261104-1000{next(counter):02d}-7f3a"
        folder.mkdir(parents=True)
        if host_files:
            for name, text in HOST_SENTINELS.items():
                (folder / name).write_text(text)
        return j2.J2Run(run_dir=folder, **kw)
    return make


def say(run, text, timeout=60.0):
    assert run.user_says(text) is True
    deadline = time.time() + timeout
    while run.status != "waiting":
        assert time.time() < deadline, "the run did not stop"
        time.sleep(0.003)


def tree_sha(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(folder).rglob("*")) if p.is_file()}


def lines(folder: Path, name: str) -> list:
    return [json.loads(x) for x in (Path(folder) / name).read_text().splitlines() if x.strip()]


@pytest.fixture
def finished(new_run):
    """A finished classic Brew Lab run (realization off)."""
    run = new_run()
    say(run, BREW_LAB)
    assert run.outcome.startswith("Done")
    return run


@pytest.fixture
def source(finished, tmp_path):
    """A copy of the finished run's folder that a test may damage."""
    copy = tmp_path / "source" / "j2-20261104-090000-0000"
    shutil.copytree(finished.dir, copy)
    return copy


# ---- (1) the classic path ----------------------------------------------------------------------------------------------
def test_a_classic_follow_up_reaches_done_with_one_more_workflow(j2, finished, new_run):
    before = tree_sha(Path(finished.dir))
    follow = new_run()
    info = follow.rehydrate(finished.dir)
    assert info == {"source": os.path.basename(finished.dir), "files": info["files"], "messages": len(finished.chat),
                    "workflows": len(finished.workflows), "sites": len(finished.sites), "realization": False}
    assert follow.done and follow.status == "waiting" and follow.outcome == finished.outcome
    say(follow, CHANGE)
    assert follow.outcome.startswith("Done"), follow.outcome
    assert len(follow.workflows) == len(finished.workflows) + 1 and len(follow.sites) == len(finished.sites) + 1
    assert follow.chat[:len(finished.chat)] == finished.chat, "the old chat is the start of the new one"
    change = follow.chat[len(finished.chat)]
    assert change["who"] == "user" and change["text"] == CHANGE and change["change"] is True
    assert follow.feedback is None or follow.feedback == CHANGE
    summary = json.loads((Path(follow.dir) / "summary.json").read_text())
    assert summary["status"] == "done" and summary["change_requests"] == [CHANGE]
    assert tree_sha(Path(finished.dir)) == before, "the old folder is never written again"


def test_the_files_are_copied_and_the_hosts_own_are_not(j2, finished, new_run):
    for name in ("task.json", "settings.json", "events.jsonl", "inbox.jsonl", "trace.jsonl", "snapshot.json", "live.json"):
        (Path(finished.dir) / name).write_text("OLD RUN'S " + name)
    (Path(finished.dir) / ".hidden.json").write_text("{}")
    (Path(finished.dir) / "upstream").mkdir()
    (Path(finished.dir) / "upstream" / "x.json").write_text("{}")
    follow = new_run()
    follow.rehydrate(finished.dir)
    new = tree_sha(Path(follow.dir))
    old = tree_sha(Path(finished.dir))
    for name, text in HOST_SENTINELS.items():
        assert (Path(follow.dir) / name).read_text() == text, f"{name} belongs to the new run"
    for gone in ("snapshot.json", "live.json", ".hidden.json", "upstream/x.json", "report.md"):
        assert gone not in new, gone
    for name in ("chat.jsonl", "calls.jsonl", "receipts.jsonl", "goal.json", "workflows.json", "summary.json", "sections.json",
                 "audits.json", "style.json", "site/v1.html", "site/index.html"):
        assert new[name] == old[name], f"{name} is copied byte for byte"
    assert any(n.startswith("site/") for n in new) and not any(n.startswith("upstream/") for n in new)


def test_calls_and_chat_continue_where_the_old_run_stopped(j2, finished, new_run):
    follow = new_run()
    follow.rehydrate(finished.dir)
    logged = len(lines(finished.dir, "calls.jsonl"))
    # the reviewer's call is counted after summary.json is written (and J2 does not log it), so the summary is one short
    assert follow.calls == json.loads((Path(finished.dir) / "summary.json").read_text())["ai_calls"] == finished.calls - 1
    assert follow.cycle == finished.cycle and (follow.spent, follow.budget) == (finished.spent, finished.budget)
    start = follow.calls
    say(follow, CHANGE)
    ids = [r["id"] for r in lines(follow.dir, "calls.jsonl")]
    assert ids == sorted(set(ids)) and ids[logged] == start + 1, "call ids continue, none repeats"
    chat = lines(follow.dir, "chat.jsonl")
    assert chat[0]["meta"] is True and [m["id"] for m in chat[1:]] == list(range(1, len(follow.chat) + 1))
    assert follow.request == BREW_LAB and follow.stamped is True


def test_rehydrate_sets_exactly_the_listed_attributes(j2, finished, new_run):
    from sutra_app.engine import rehydrate as R
    follow = new_run()
    before = dict(vars(follow))
    follow.rehydrate(finished.dir)
    after = vars(follow)
    changed = {k for k in after if after[k] is not before.get(k) and after[k] != before.get(k)}
    assert changed <= set(R.RESTORED) and {"chat", "goal", "workflows", "sites", "done", "status", "outcome", "request"} <= changed
    assert not (set(R.RESTORED_REALIZATION) & changed), "no realization.json: no real*"
    assert set(after) == set(before), "no attribute was added"


def test_decisions_and_the_answered_questions_come_back(j2, new_run):
    run = new_run()
    for text in VAGUE:
        say(run, text)
    assert run.outcome.startswith("Done") and len(run.decisions) == 2
    follow = new_run()
    follow.rehydrate(run.dir)
    assert follow.decisions == run.decisions and follow.conflicts == run.conflicts
    say(follow, CHANGE)
    assert follow.outcome.startswith("Done") and len(follow.workflows) >= len(run.workflows)


def test_a_board_recheck_in_audits_json_is_not_an_audit(j2, source, new_run):
    audits = json.loads((source / "audits.json").read_text())
    (source / "audits.json").write_text(json.dumps(audits + [{"kind": "recheck", "trigger": "Q-1"}]))
    follow = new_run()
    follow.rehydrate(source)
    assert len(follow.audits) == len(audits) and all(a.get("kind") != "recheck" for a in follow.audits)


def test_files_that_a_run_may_lack_are_optional(j2, source, new_run):
    for name in ("sections.json", "style.json", "conflicts.json", "audits.json", "receipts.jsonl", "calls.jsonl"):
        (source / name).unlink()
    follow = new_run()
    follow.rehydrate(source)
    assert follow.sections == {} and follow.style is None and follow.conflicts == [] and follow.audits == [] and follow.receipts == []
    assert follow.calls == json.loads((source / "summary.json").read_text())["ai_calls"]


def test_the_call_counter_never_falls_behind_calls_jsonl(j2, source, new_run):
    summary = json.loads((source / "summary.json").read_text())
    summary["ai_calls"] = 2
    (source / "summary.json").write_text(json.dumps(summary))
    follow = new_run()
    follow.rehydrate(source)
    assert follow.calls == max(r["id"] for r in lines(source, "calls.jsonl")) > 2


def test_links_in_the_old_folder_are_not_followed(j2, source, new_run, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("secret")
    os.symlink(outside, source / "site" / "evil.html")
    os.symlink(outside, source / "evil.json")
    follow = new_run()
    follow.rehydrate(source)
    assert not (Path(follow.dir) / "site" / "evil.html").exists() and not (Path(follow.dir) / "evil.json").exists()


def test_a_source_that_is_a_link_is_refused(j2, source, new_run, tmp_path):
    link = tmp_path / "link"
    os.symlink(source, link)
    from sutra_app.engine.rehydrate import RehydrateRefused
    with pytest.raises(RehydrateRefused, match="folder is not there"):
        new_run().rehydrate(link)


# ---- (2) realization on, with an Adaptation reply that carries estimated_resources.money ------------------------------
def money_port():
    """A ScriptedPort whose Adaptation replies carry estimated_resources.money, as a real Adaptation's do."""
    from sutra_app.engine.llm import ScriptedPort

    class MoneyPort(ScriptedPort):
        def complete(self, req, on_progress=None):
            inner = req.scripted
            if req.tag.function == "adaptation" and inner is not None:
                def scripted():
                    text = inner()
                    try:
                        data = json.loads(text)
                    except ValueError:
                        return text
                    for w in data.get("workflows") or []:
                        if isinstance(w, dict) and "estimated_resources" not in w:
                            w["estimated_resources"] = {"money": 10, "calls": 2, "time_minutes": 5}
                    return json.dumps(data)
                req = req.model_copy(update={"scripted": scripted})
            return super().complete(req, on_progress)
    return MoneyPort()


@pytest.fixture
def realized(new_run, monkeypatch):
    monkeypatch.setenv("J2_REALIZATION", "1")
    run = new_run()
    say(run, BREW_LAB)
    assert run.outcome.startswith("Done") and run.real is not None
    return run


def test_a_follow_up_with_realization_on_reaches_done_when_adaptation_estimates_the_money(j2, realized, new_run, mock_mode):
    mock_mode.configure(money_port(), mock=True)
    follow = new_run()
    info = follow.rehydrate(realized.dir)
    assert info["realization"] is True and (Path(follow.dir) / "realization.json").is_file()
    assert follow.real == json.loads((Path(realized.dir) / "realization.json").read_text())
    assert follow.real_base == follow.goal and follow.real_base is not follow.goal, "a copy of the charter"
    assert follow.real_asked is True and "applied" not in follow.real_summary and follow.real_summary["proposal_brief"]
    say(follow, CHANGE)
    assert follow.outcome.startswith("Done") and follow.paused is None, follow.outcome
    assert len(follow.workflows) == len(realized.workflows) + 1


def test_without_estimates_the_realization_follow_up_pauses_as_it_does_without_rehydrate(j2, realized, new_run):
    """The control: J2's mock Adaptation reply for a change after Done has no estimated_resources, and with realization on
    there is no rate card, so every workflow costs 0 and the validator refuses it. Not a defect of rehydrate (design section 2)."""
    follow = new_run()
    follow.rehydrate(realized.dir)
    say(follow, CHANGE)
    assert follow.paused and follow.paused["kind"] == "limit"
    assert any("its cost is 0" in m["text"] for m in follow.chat if m["who"] == "system")
    same_process = realized
    say(same_process, CHANGE)
    assert same_process.paused and any("its cost is 0" in m["text"] for m in same_process.chat if m["who"] == "system")


# ---- (4) refusals -------------------------------------------------------------------------------------------------------
def refused(run, source):
    from sutra_app.engine.rehydrate import RehydrateRefused
    before = dict(vars(run)), sorted(os.listdir(run.dir))
    with pytest.raises(RehydrateRefused) as caught:
        run.rehydrate(source)
    assert (dict(vars(run)), sorted(os.listdir(run.dir))) == before, "a refusal changes nothing"
    return caught.value.reason


def edit_json(path: Path, **changes):
    data = json.loads(path.read_text())
    data.update(changes)
    path.write_text(json.dumps(data))


def test_an_unfinished_source_is_refused(j2, source, new_run):
    (source / "summary.json").unlink()
    assert refused(new_run(), source) == "the earlier run left no summary, so it never finished"


@pytest.mark.parametrize("status,reason", [("stopped", "the earlier run was stopped before it finished"),
                                           ("crashed", "the earlier run crashed"),
                                           ("running", "the earlier run did not finish (running)")])
def test_a_stopped_crashed_or_unfinished_source_is_refused(j2, source, new_run, status, reason):
    edit_json(source / "summary.json", status=status)
    assert refused(new_run(), source) == reason


def test_a_done_with_open_items_source_is_allowed(j2, source, new_run):
    edit_json(source / "summary.json", status="done_with_open_items", outcome="Done with open items: shipped as is.")
    follow = new_run()
    follow.rehydrate(source)
    assert follow.outcome == "Done with open items: shipped as is."


def test_a_source_whose_output_is_not_a_website_is_refused(j2, source, new_run):
    rows = (source / "chat.jsonl").read_text().splitlines()
    rows[0] = json.dumps({**json.loads(rows[0]), "output": "prd"})
    (source / "chat.jsonl").write_text("\n".join(rows) + "\n")
    assert refused(new_run(), source) == "the earlier run built a prd, not a website"


def test_a_source_without_a_chat_header_is_refused(j2, source, new_run):
    rows = (source / "chat.jsonl").read_text().splitlines()
    (source / "chat.jsonl").write_text("\n".join(rows[1:]) + "\n")
    assert refused(new_run(), source) == "the earlier run's chat.jsonl has no header"


@pytest.mark.parametrize("name", ["documents.json", "stage-prd.json"])
def test_a_stray_document_chain_file_without_a_described_chain_is_refused(j2, source, new_run, name):
    """E1-b lifted the refusal of a document chain (see test_engine_rehydrate_chain.py); a chain file that `summary.json` does
    not describe is still not a chain J2 can carry on."""
    (source / name).write_text("{}")
    assert "document chain cannot be read" in refused(new_run(), source)


@pytest.mark.parametrize("name,reason", [("goal.json", "the earlier run has no charter (goal.json)"),
                                         ("workflows.json", "the earlier run has no workflows (workflows.json)")])
def test_a_source_without_its_charter_or_workflows_is_refused(j2, source, new_run, name, reason):
    (source / name).unlink()
    assert refused(new_run(), source) == reason


@pytest.mark.parametrize("name", ["goal.json", "workflows.json", "summary.json", "sections.json", "realization.json"])
def test_an_unreadable_file_is_refused(j2, source, new_run, name):
    (source / name).write_text("{not json")
    assert refused(new_run(), source) == f"{name} cannot be read"


def test_a_file_of_the_wrong_kind_is_refused(j2, source, new_run):
    (source / "workflows.json").write_text('{"a": 1}')
    assert refused(new_run(), source) == "workflows.json does not hold a list"


def test_a_missing_folder_is_refused(j2, new_run, tmp_path):
    assert refused(new_run(), tmp_path / "nowhere") == "the earlier run's folder is not there"


def test_rehydrate_continues_a_finished_document_chain(j2, new_run, tmp_path):
    """E1-b (GAP-E1B): the limit is lifted. A finished PRD, HLD, LLD and website chain is brought back; the details are in
    test_engine_rehydrate_chain.py."""
    chain = new_run()
    chain.budget = 900
    say(chain, BREW_LAB + " Write the design docs first. Users: coffee lovers and office staff. Problem: people can't see the "
        "menu or order ahead. Must-have features: see the menu with prices, pre-order a coffee, find the shop, read the "
        "opening hours. Constraints: one page only. Success: 30 pre-orders per week.", timeout=120)
    assert chain.outcome.startswith("Done") and chain.stages == ["prd", "hld", "lld", "website"]
    follow = new_run()
    info = follow.rehydrate(chain.dir)
    assert follow.stages == chain.stages and follow.stage_i == 3 and follow.docset == ["prd", "hld", "lld"] and follow.done
    assert info["workflows"] == len(chain.past_workflows) + len(chain.workflows)


def test_a_run_that_has_already_started_cannot_be_rehydrated(j2, finished, new_run, source):
    with pytest.raises(ValueError, match="has not started"):
        finished.rehydrate(source)
    started = new_run()
    started.post("system", "Context from the team lead: hello")
    with pytest.raises(ValueError, match="has not started"):
        started.rehydrate(source)
    stray = new_run()
    (Path(stray.dir) / "chat.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="has not started"):
        stray.rehydrate(source)


def test_a_copy_that_fails_half_way_is_undone(j2, source, new_run, monkeypatch):
    follow = new_run()
    before = dict(vars(follow)), tree_sha(Path(follow.dir))
    real, count = shutil.copyfile, itertools.count()

    def flaky(src, dst, *a, **k):
        if next(count) == 12:
            raise OSError(28, "No space left on device")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(shutil, "copyfile", flaky)
    from sutra_app.engine.rehydrate import RehydrateRefused
    with pytest.raises(RehydrateRefused, match=r"could not be copied \(No space left on device\)"):
        follow.rehydrate(source)
    assert (dict(vars(follow)), tree_sha(Path(follow.dir))) == before
    assert not (Path(follow.dir) / "site").exists() and not (Path(follow.dir) / "artifacts").exists(), "no empty folders left"


# ---- the fixed system lines ------------------------------------------------------------------------------------------------
def test_the_two_system_lines_are_fixed(j2):
    from sutra_app.engine.rehydrate import continuing_line, fresh_line
    assert continuing_line("j2-20261104-100004-7f3a") == (
        "Continuing from run j2-20261104-100004-7f3a: the team keeps its charter, workflows, findings and site and treats "
        "your message as a change request.")
    assert fresh_line("j2-20261104-100004-7f3a", "the earlier run crashed") == (
        "Starting a new run. Your earlier files from run j2-20261104-100004-7f3a are in upstream/j2-20261104-100004-7f3a/ "
        "for reference. Reason: the earlier run crashed.")
    assert fresh_line("j2-x", "it was stopped. ") == "Starting a new run. Your earlier files from run j2-x are in upstream/j2-x/ for reference. Reason: it was stopped."
