"""test_j2ui_render.py -- the prototype's captured answers
(UI port, package j2ui-verify, step T1; step T2 adds the render proof).

Named claims:
  T1-1  test_fixtures/j2ui/captured holds the prototype's own answers for four real runs and the idle live state: every endpoint
        of each, under 3 MB in all; SOURCE.json names the pinned commit and the hash of every file, and they match
  T1-2  each state fixture has exactly the 56 keys of j2ui_common.STATE_KEYS (the live state in the same order; a saved run's
        snapshot leads with `saved`, which the page does not mind)
  T1-3  scripts/capture_j2_fixtures.py refuses a scratch or output folder inside the prototype's folder; run for real (when the
        prototype is here) it makes the same bytes as the committed fixtures and leaves `git status --short` of the prototype as it was

Run: ./run-tests.sh test_j2ui_render.py"""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from test_fixtures.j2ui import harness as H
from test_fixtures.j2ui import proto
from test_fixtures.j2ui.core_fixtures import *  # noqa: F401,F403  (mods)

import j2ui_common as C

UI = Path(__file__).resolve().parent
RUNS = ("j2-20261008-153402", "j2-20261008-123848", "j2-20261014-111512", "j2-20261022-123744")
ENDPOINTS = ("state", "map", "board", "artifacts", "docs", "audits", "refs", "runs")


def script(name="capture_j2_fixtures"):
    spec = importlib.util.spec_from_file_location(name, str(UI / "scripts" / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- T1: the fixtures --------------------------------------------------------------------------------------------------------
def test_t1_the_captured_runs_are_here_with_every_endpoint_and_are_small():
    assert H.captured_runs() == sorted(RUNS + ("idle",))
    total = 0
    for run in H.captured_runs():
        for name in ENDPOINTS:
            path = H.CAPTURED / run / (name + ".json.gz")
            assert path.is_file(), path
            total += path.stat().st_size
    for path in H.CAPTURED.rglob("*"):
        if path.is_file():
            assert path.stat().st_size > 0, path
    assert total < 3 * 1024 * 1024, total
    assert sum(p.stat().st_size for p in H.CAPTURED.rglob("*") if p.is_file()) < 3 * 1024 * 1024


def test_t1_source_json_names_the_commit_and_every_files_hash():
    src = json.loads((H.CAPTURED / "SOURCE.json").read_text(encoding="utf-8"))
    pin = json.loads((UI / "j2ui_assets" / "PINNED.json").read_text(encoding="utf-8"))["source"]["commit"]
    assert src["schema"] == "j2ui-captured/1" and src["commit"] == pin == proto.PIN
    assert [r["id"] for r in src["runs"]] == list(RUNS) + ["idle"]
    seen = 0
    for row in src["runs"]:
        for name, meta in row["files"].items():
            data = (H.CAPTURED / row["id"] / (name + ".json.gz")).read_bytes()
            assert hashlib.sha256(data).hexdigest() == meta["sha256"] and len(data) == meta["bytes"], (row["id"], name)
            seen += 1
    assert seen == sum(1 for p in H.CAPTURED.rglob("*.json.gz"))


@pytest.mark.parametrize("run", ["idle"] + list(RUNS))
def test_t1_each_state_has_exactly_the_56_keys(run):
    state = H.captured(run, "state")
    assert len(C.STATE_KEYS) == 56
    assert sorted(state) == sorted(C.STATE_KEYS) and len(state) == 56
    if run == "idle":
        assert list(state) == list(C.STATE_KEYS), "the order the prototype sends the live state in is the order the adapter sends it in"
    assert state["saved"] == (None if run == "idle" else run)


def test_t1_no_path_of_a_machine_and_no_secret_is_in_a_fixture():
    for path in H.CAPTURED.rglob("*.json.gz"):
        text = gzip.decompress(path.read_bytes()).decode("utf-8")
        assert "/Users/" not in text and "/home/" not in text, path
        assert "sk-ant" not in text and "AKIA" not in text, path


def test_t1_the_capture_script_never_writes_inside_the_prototype(tmp_path):
    cap = script()
    repo = tmp_path / "proto"
    (repo / "runs").mkdir(parents=True)
    with pytest.raises(cap.Refused):
        cap.refuse_inside(repo, repo / "scratch")
    with pytest.raises(cap.Refused):
        cap.refuse_inside(repo, tmp_path / "elsewhere", repo / "runs" / "x" / "out")
    cap.refuse_inside(repo, tmp_path / "scratch", tmp_path / "out")
    link = tmp_path / "link"
    link.symlink_to(repo, target_is_directory=True)
    with pytest.raises(cap.Refused):
        cap.refuse_inside(repo, link / "scratch")
    assert cap.inside(repo, repo) and not cap.inside(tmp_path, repo)


def test_t1_the_capture_script_says_so_and_stands_down_when_the_prototype_is_not_here(tmp_path, capsys):
    cap = script()
    assert cap.main(["--prototype", str(tmp_path / "nothing-here"), "--out", str(tmp_path / "out")]) == 0
    assert "committed fixtures stand" in capsys.readouterr().out and not (tmp_path / "out").exists()


def test_t1_the_capture_script_reproduces_the_committed_bytes_and_leaves_the_prototype_alone(tmp_path):
    reason = proto.skip_reason()
    repo = proto.repo()
    if reason or not (repo / "runs" / RUNS[0]).is_dir():
        print("j2ui tests: " + (reason or "the prototype has no runs/%s here" % RUNS[0]))
        pytest.skip(reason or "no prototype runs here")
    cap = script()
    before = cap.status_of(repo)
    out = tmp_path / "captured"
    assert cap.main(["--prototype", str(repo), "--out", str(out), "--runs", RUNS[0]]) == 0
    assert cap.status_of(repo) == before, "git status --short of the prototype is as it was"
    for name in ENDPOINTS:                      # the same answers (the bytes of the gzip may differ with the zlib that made them)
        got = json.loads(gzip.decompress((out / RUNS[0] / (name + ".json.gz")).read_bytes()).decode("utf-8"))
        if name == "runs":                      # the list of saved runs is of the runs this capture kept; the live id is of the minute
            assert [r["id"] for r in got["runs"]] == [RUNS[0]] and set(got) == {"live", "runs"}
            continue
        assert got == H.captured(RUNS[0], name), name
    assert json.loads((out / "SOURCE.json").read_text(encoding="utf-8"))["commit"] == proto.PIN
