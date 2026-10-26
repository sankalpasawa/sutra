"""test_j2ui_render.py -- the captured fixtures, and the proof that the copy of the page draws what the prototype's page draws
(UI port, package j2ui-verify, steps T1 and T2).

Named claims:
  T1-1  test_fixtures/j2ui/captured holds the prototype's own answers for four real runs and the idle live state: every endpoint
        of each, under 3 MB in all; SOURCE.json names the pinned commit and the hash of every file, and they match
  T1-2  each state fixture has exactly the 56 keys of j2ui_common.STATE_KEYS (the live state in the same order; a saved run's
        snapshot leads with `saved`, which the page does not mind)
  T1-3  scripts/capture_j2_fixtures.py refuses a scratch or output folder inside the prototype's folder; run for real (when the
        prototype is here) it makes the same bytes as the committed fixtures and leaves `git status --short` of the prototype as it was
  T2-1  the page, polled by test_fixtures/j2ui/poll_harness.js against each captured run, is ok on the pinned prototype page and on
        j2ui_assets/j2_ui.html, and every pane is identical once the prototype's output has substitution S1 applied
  T2-2  the harness is not a rubber stamp: a state with a key missing, a pane that says undefined, a state the server will not give
        and a hand edit of the copy's script each turn it red
  T2-3  the pinned j2_ui_render.js runs on the same states without throwing, and its output on the copy equals the prototype page's
  T2-4  j2ui_assets/j2_schema.py is the file j2ui_atoms loads, and atoms_v1 of a department is run_views of its workflows by it

Run: ./run-tests.sh test_j2ui_render.py"""
import gzip
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from test_fixtures.j2ui import harness as H
from test_fixtures.j2ui import proto
from test_fixtures.j2ui.core_fixtures import *  # noqa: F401,F403  (mods, born)

import j2ui_common as C

UI = Path(__file__).resolve().parent
COPY = UI / "j2ui_assets" / "j2_ui.html"
RENDER_JS = UI / "test_fixtures" / "j2ui" / "j2_ui_render.js"
RUNS = ("j2-20261008-153402", "j2-20261008-123848", "j2-20261014-111512", "j2-20261022-123744")
ENDPOINTS = ("state", "map", "board", "artifacts", "docs", "audits", "refs", "runs")


def script(name="capture_j2_fixtures"):
    spec = importlib.util.spec_from_file_location(name, str(UI / "scripts" / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pinned_page():
    return proto.show("j2_ui.html").decode("utf-8")


def differing(prototype_out, copy_out):
    """The panes whose HTML differs, the prototype's output taken after S1 (the one substitution that reaches rendered output)."""
    keys = set(prototype_out["panes"]) | set(copy_out["panes"])
    return sorted(k for k in keys if H.s1(prototype_out["panes"].get(k, "")) != copy_out["panes"].get(k, ""))


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


# ---- T2: the same page draws the same -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("run", ["idle"] + list(RUNS))
def test_t2_the_copy_draws_every_pane_as_the_prototype_does_on_the_prototypes_real_data(run):
    bundle = H.bundle_of(run)
    theirs = H.run_harness(pinned_page(), bundle)
    ours = H.run_harness(COPY, bundle)
    assert theirs["ok"], ("the pinned prototype page", theirs["errors"])
    assert ours["ok"], ("the copy", ours["errors"])
    assert theirs["polls"] == ours["polls"] == 3 and theirs["posts"] == ours["posts"] == []
    assert differing(theirs, ours) == []
    if run != "idle":
        assert ours["panes"]["smsgs"] and ours["panes"]["pane-goal"] and ours["panes"]["renderMap"], "panes with something in them"


def test_t2_the_panes_hold_the_runs_real_content_so_the_comparison_is_not_empty():
    ours = H.run_harness(COPY, H.bundle_of("j2-20261022-123744"))
    panes = ours["panes"]
    assert len(panes["pane-workflows"]) > 100000 and "W-1.a1" in panes["pane-workflows"]
    assert "<svg" in panes["renderMap"] and "mapnode" in panes["renderMap"]
    assert "Deliverables" in panes["renderArtifacts"] and "artrow" in panes["renderArtifacts"]
    assert panes["renderDocs"] and panes["pane-timeline"] and panes["pane-audit"]
    assert panes["msgs"].count("<div class=\"msg ") > 100
    assert len(H.run_harness(COPY, H.bundle_of("idle"))["panes"]["smsgs"]) > 100, "the idle start screen has its examples"


def test_t2_a_state_with_a_key_missing_is_not_ok(tmp_path):
    for key in ("atoms_v1", "paused", "report", "workable"):
        bundle = H.bundle_of("j2-20261014-111512")
        del bundle["state"][key]
        got = H.run_harness(COPY, bundle)
        assert not got["ok"] and any("lacks " + key in e for e in got["errors"]), (key, got["errors"])


def test_t2_a_pane_that_says_undefined_nan_or_null_is_not_ok():
    for word in ("undefined", "NaN", "null"):
        bundle = H.bundle_of("j2-20261008-153402")
        bundle["state"]["goal"]["statement"] = "A shop that sells %s kurtas" % word
        got = H.run_harness(COPY, bundle)
        assert not got["ok"] and any(word in e for e in got["errors"]), (word, got["errors"])
    fine = H.bundle_of("j2-20261008-153402")
    fine["state"]["goal"]["statement"] = "A shop that sells nullable and undefinedly named kurtas, price NaNa"
    assert H.run_harness(COPY, fine)["ok"], "a word is a whole word: nullable is not null"


def test_t2_a_state_the_server_will_not_give_is_not_ok():
    bundle = H.bundle_of("idle")
    del bundle["state"]
    got = H.run_harness(COPY, bundle)
    assert not got["ok"] and got["sstatus"] == "Something went wrong. Try again."
    assert any("still null" in e for e in got["errors"]), got["errors"]


def test_t2_a_state_the_page_cannot_draw_is_not_ok_and_the_error_is_named():
    bundle = H.bundle_of("j2-20261014-111512")
    bundle["state"]["workflows"] = None
    got = H.run_harness(COPY, bundle)
    assert not got["ok"] and any("renderWorkflows" in e for e in got["errors"]), got["errors"]


def test_t2_a_hand_edit_of_the_copys_script_is_seen_in_the_panes(tmp_path):
    text = COPY.read_text(encoding="utf-8")
    for run, old, new in (("idle", "Nothing recorded yet.", "Nothing recorded."), ("idle", "Nothing built yet.", "Not built."),
                          ("j2-20261008-123848", "Deliverables", "Things made")):
        bundle = H.bundle_of(run)
        theirs = H.run_harness(pinned_page(), bundle)
        assert old in text
        edited = tmp_path / "edited.html"
        edited.write_text(text.replace(old, new), encoding="utf-8")
        got = H.run_harness(edited, bundle)
        assert got["ok"]
        assert differing(theirs, got), "a changed label turns the comparison red: " + old


def test_t2_a_page_that_reads_a_new_url_fails_the_comparison(tmp_path):
    bundle = H.bundle_of("j2-20261022-123744")
    theirs = H.run_harness(pinned_page(), bundle)
    text = COPY.read_text(encoding="utf-8")
    edited = tmp_path / "edited.html"
    assert "`api/map?" in text
    edited.write_text(text.replace("`api/map?", "`api/map2?", 1), encoding="utf-8")
    assert differing(theirs, H.run_harness(edited, bundle)), "the Map is not drawn when the page asks for another URL"


# ---- T2-3: the prototype's own render harness ------------------------------------------------------------------------------------
def render_js(page, run, tmp):
    """The pinned j2_ui_render.js on a page and a captured run: its JSON, or the error."""
    H.need_node()
    d = Path(tmp)
    (d / "state.json").write_text(json.dumps(H.captured(run, "state")), encoding="utf-8")
    (d / "previews.json").write_text("{}", encoding="utf-8")
    (d / "docs.json").write_text(json.dumps({
        "map": H.captured(run, "map"), "artifacts": H.captured(run, "artifacts"), "board": (H.captured(run, "board") or {}).get("entries", []),
        "docs": H.captured(run, "docs"), "refs": H.captured(run, "refs")}), encoding="utf-8")
    got = subprocess.run(["node", str(RENDER_JS), str(page), str(d / "state.json"), str(d / "previews.json"), str(d / "docs.json")],
                         capture_output=True, timeout=120, check=False)
    assert got.returncode == 0, got.stderr.decode("utf-8", "replace")[-500:]
    return json.loads(got.stdout.decode("utf-8"))


def test_t2_the_pinned_render_js_runs_on_every_state_and_agrees_across_the_two_pages(tmp_path):
    assert hashlib.sha256(RENDER_JS.read_bytes()).hexdigest() == json.loads(
        (UI / "j2ui_assets" / "PINNED.json").read_text(encoding="utf-8"))["source"]["files"]["j2_ui_render.js"]["sha256"]
    pinned = tmp_path / "pinned.html"
    pinned.write_text(pinned_page(), encoding="utf-8")
    for run in ["idle"] + list(RUNS):
        ours = render_js(COPY, run, tmp_path)
        theirs = render_js(pinned, run, tmp_path)
        assert {"simple", "sprog", "cards", "workflows", "charter", "docs", "artifacts", "map", "board", "needs"} <= set(ours), run
        assert len(ours["cards"]) == len(H.captured(run, "state")["workflows"]), run
        assert json.loads(H.s1(json.dumps(theirs))) == ours, run


# ---- T2-4: atoms_v1 is the vendored schema's ------------------------------------------------------------------------------------
def test_t2_the_vendored_schema_is_the_file_atoms_loads_and_atoms_v1_is_its_run_views(mods, born):
    import j2ui_atoms as A
    import j2ui_work as K
    vendored = UI / "j2ui_assets" / "j2_schema.py"
    assert A.ASSET == vendored and vendored.is_file()
    mod = A.schema()
    assert mod is not None and Path(mod.__file__).resolve() == vendored.resolve()
    assert hashlib.sha256(vendored.read_bytes()).hexdigest() == hashlib.sha256(proto.show("j2_schema.py")).hexdigest(), "the prototype's file"
    ref = born()
    ctx = C.get_ctx(ref)
    built = K.build(ctx)
    assert built["workflows"] and built["atoms_v1"], "a department that has run has workflows and atom views"
    views, _warnings = mod.run_views(built["workflows"])
    assert built["atoms_v1"] == {v["id"]: v for v in views}
    assert not [w for w in mod.validate_views(list(built["atoms_v1"].values())) if "missing" in w], "no view lacks an atom"
