"""Strict mode accepts every file of mock runs of the vendored J2 with the reuse flags in every state (J2 sync 6, D186; lane L done-when):
flags off, auto-reuse on, the content door on (a first run, the same brief served from it, another business over its template), and a run
template chosen by name. The runs are made by `reuse_runs.py` in a child process (J2 reads its environment at import, and the run is a
real mock run of the engine); the six runs take about ten seconds. The tests of the same models on small files cut from such runs are
in `test_lib_reuse.py`.

Every file is checked by `gate_record` in strict mode, so a key J2 writes that a model does not know, or a file the catalogue does not know,
fails here with its path; the library's own versions (the seed and what the runs stored) are checked as `template.meta` and the run templates
as `RunTemplateBundle`."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sutra_app.library import records as R
from sutra_app.library.templates import RunTemplateBundle, TemplateMeta
from sutra_app.ops import doctor

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
RUNS = ("off", "auto", "door1", "door2", "door3", "tpl")

@pytest.fixture(scope="module")
def runs(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("reuse-runs") / "out"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("J2_", "STUDIO_", "SUTRA_"))}
    env["PYTHONPATH"] = str(REPO) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    done = subprocess.run([sys.executable, "-u", str(HERE / "reuse_runs.py"), str(out), str(doctor.seed_dir())], cwd=out.parent, env=env,
                          capture_output=True, text=True, timeout=900)
    assert done.returncode == 0 and "runs done" in done.stdout, done.stdout[-1500:] + done.stderr[-3000:]
    assert "set_run_template: True" in done.stdout
    return out


def json_rows(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return [json.loads(text)]


def strict_problems(run: Path) -> list[str]:
    found = []
    for path in sorted(p for p in run.rglob("*") if p.is_file()):
        rel = path.relative_to(run).as_posix()
        try:
            rows = json_rows(path) if path.suffix in (".json", ".jsonl") else [None]
            for row in rows:
                R.gate_record(rel, row, mode="strict")
        except R.RecordRejected as exc:
            found.append(f"{rel}: {exc}")
    return found


@pytest.mark.parametrize("name", RUNS)
def test_strict_mode_accepts_every_file_of_the_run(runs, name):
    files = [p for p in (runs / name).rglob("*") if p.is_file()]
    assert len(files) > 20 and (runs / name / "summary.json").is_file()
    assert strict_problems(runs / name) == []


def test_the_flags_show_in_the_files_each_state_is_meant_to_write(runs):
    assert not (runs / "off" / "reuse.json").exists() and not (runs / "off" / "templates.json").exists()      # the library is off: no routing file
    auto = json.loads((runs / "auto" / "templates.json").read_text())
    assert auto["auto_reuse"]["picked"] and auto["run_template"]["auto"] is True
    assert not (runs / "auto" / "reuse.json").exists()
    door = json.loads((runs / "door2" / "reuse.json").read_text())
    assert {d["door"] for d in door["decisions"]} == {"reuse"} and all(d["held"] and d["refunded"] for d in door["decisions"])
    assert any(d.get("new_family") for d in json.loads((runs / "door3" / "templates.json").read_text())["decisions"])
    tpl = json.loads((runs / "tpl" / "templates.json").read_text())
    assert tpl["run_template"]["selected"] == ["W-1", "W-3"] and tpl["run_template"]["id"] == "thread-boutique-website"
    head = json.loads((runs / "door2" / "chat.jsonl").read_text().splitlines()[0])
    assert head["by"] == "sutra-pro"


def test_every_version_the_runs_stored_validates_and_every_run_template_is_a_bundle(runs):
    library = runs / "library"
    versions = sorted(library.glob("*/*/*/v*/meta.json"))
    assert len(versions) > len(list(doctor.seed_dir().glob("*/*/*/v*/meta.json")))             # the runs added versions of their own
    for path in versions:
        TemplateMeta.model_validate(json.loads(path.read_text(encoding="utf-8")))
    bundles = sorted(library.glob("run-templates/*/template.json"))
    assert any(p.parent.name == "a-rerun-of-still-point-yoga" for p in bundles)
    for path in bundles:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert RunTemplateBundle.model_validate(data).id == path.parent.name
