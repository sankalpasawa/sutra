"""J2's own scripts, ported, as subprocess suites (work package E5, engine design 9, ENG-01 and ENG-10).

`tests/engine/legacy/` holds `j2_flow_test.py`, `change_test.py`, `realization_test.py` and `j2_replay_size.py` from J2 `33aeeda` with
only the edits the engine design lists (sibling imports point to `sutra_app.engine`; J2's page, harness files and saved runs are read
from `SUTRA_J2_CHECKOUT` and the block that needs them prints a skip reason when it is unset; no git history; no real `claude`). Each
script runs here in a child process with a clean environment and a temp folder as its working directory, because it sets J2's
environment at import and mutates module state. The flow script takes minutes and is marked slow (`SUTRA_SLOW=1`); the two small
scripts take a few seconds and run in every gate. The other tests check the edits themselves: the skip mechanism, the generated PNG,
the paths that follow `SUTRA_J2_CHECKOUT`, and `scripts/engine_gate.sh`.
"""
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
LEGACY = HERE / "legacy"
GATE = REPO / "scripts" / "engine_gate.sh"
EXPECTED = json.loads((LEGACY / "EXPECTED.json").read_text(encoding="utf-8"))


def clean_env(**extra) -> dict:
    """The environment a script gets: no J2_, STUDIO_ or SUTRA_ variable of this session, the repo on PYTHONPATH."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("J2_", "STUDIO_", "SUTRA_"))}
    env["PYTHONPATH"] = str(REPO) + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def run_script(args, tmp_path, timeout=120, **extra_env) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-u", str(LEGACY / args[0]), *args[1:]], cwd=tmp_path, env=clean_env(**extra_env),
                          capture_output=True, text=True, timeout=timeout)


def run_python(code: str, tmp_path, **extra_env) -> subprocess.CompletedProcess:
    """`code` in a child with the legacy folder first on the path, so that `import j2_flow_test` finds the ported script."""
    return subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(LEGACY)!r})\n" + textwrap.dedent(code)],
                          cwd=tmp_path, env=clean_env(**extra_env), capture_output=True, text=True, timeout=120)


# ---- the recorded minimums --------------------------------------------------------------------------------------------------
def test_expected_json_records_the_three_minimums():
    assert set(EXPECTED) == {"j2_commit", "flow_fast_ok_lines", "change_checks", "realization_checks"}
    assert EXPECTED["j2_commit"].startswith("9200cf6")
    assert EXPECTED["change_checks"] >= 192 and EXPECTED["realization_checks"] >= 97       # J2's own numbers (engine.md 9)
    assert EXPECTED["flow_fast_ok_lines"] >= 60


def test_the_four_scripts_are_there_and_use_the_engine_package():
    assert sorted(p.name for p in LEGACY.glob("*.py")) == ["change_test.py", "j2_flow_test.py", "j2_replay_size.py", "realization_test.py"]
    for path in LEGACY.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?m)^\s*import (?!j2_flow_test)(j2[a-z_]*|llm)( as \w+)?\s*(#.*)?$", text), path.name       # no bare sibling import left
        assert "fingerprint(REAL_MEMORY)" not in text and "\"docs\", \"ui-simple-start-390.png\"" not in text, path.name
    assert 'if shutil.which("claude") and os.environ.get("SUTRA_LIVE") == "1"' in (LEGACY / "j2_flow_test.py").read_text(encoding="utf-8")


# ---- the scripts as subprocesses ----------------------------------------------------------------------------------------------
def test_change_script_passes(tmp_path):
    res = run_script(["change_test.py"], tmp_path)
    assert res.returncode == 0, res.stdout[-800:] + res.stderr[-1500:]
    n = int(re.search(r"(\d+) checks passed", res.stdout).group(1))
    assert n >= EXPECTED["change_checks"] >= 192 and "Traceback" not in res.stderr


def test_realization_script_passes(tmp_path):
    res = run_script(["realization_test.py"], tmp_path)
    assert res.returncode == 0, res.stdout[-800:] + res.stderr[-1500:]
    n = int(re.search(r"(\d+) checks passed", res.stdout).group(1))
    assert n >= EXPECTED["realization_checks"] >= 97 and "Traceback" not in res.stderr


@pytest.mark.slow
def test_flow_script_fast_passes(tmp_path):
    """`j2_flow_test.py --fast`: both J2_FIXES modes, every block the engine can run without J2's page files (about 5 minutes)."""
    res = run_script(["j2_flow_test.py", "--fast"], tmp_path, timeout=600)
    tail = res.stdout.strip().splitlines()[-1:] or [""]
    assert res.returncode == 0, res.stdout[-1500:] + res.stderr[-2500:]
    assert tail == ["j2 flow checks passed"] and "Traceback" not in res.stdout + res.stderr
    assert sum(1 for line in res.stdout.splitlines() if line.endswith(" ok")) >= EXPECTED["flow_fast_ok_lines"]


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("SUTRA_BROWSER") != "1", reason="needs Chrome and node: set SUTRA_BROWSER=1")
def test_flow_script_fast_browser_passes(tmp_path):
    res = run_script(["j2_flow_test.py", "--fast", "--browser"], tmp_path, timeout=1200,
                     **({"SUTRA_J2_CHECKOUT": os.environ["SUTRA_J2_CHECKOUT"]} if os.environ.get("SUTRA_J2_CHECKOUT") else {}))
    assert res.returncode == 0, res.stdout[-1500:] + res.stderr[-2500:]
    assert res.stdout.strip().splitlines()[-1] == "j2 flow checks passed"


# ---- the edits themselves ---------------------------------------------------------------------------------------------------
def test_without_a_checkout_a_page_block_skips_with_a_reason_and_leaves_no_trace(tmp_path):
    res = run_python("""
        import os
        import j2_flow_test as F
        before = dict(os.environ)
        F.artifact_types()                         # reads J2's page after its engine checks
        assert dict(os.environ) == before, "the environment is put back"
        print("HERE", F.HERE == F.LEGACY_DIR)
        """, tmp_path)
    assert res.returncode == 0, res.stderr[-1500:]
    assert "skipped the rest of artifact_types: j2_ui.html not found (set SUTRA_J2_CHECKOUT to a J2 checkout)" in res.stdout
    assert "HERE True" in res.stdout


def test_skip_restores_what_a_block_changed_before_it_stopped(tmp_path):
    res = run_python("""
        import os
        import j2_flow_test as F
        from sutra_app.engine import j2

        def block():
            os.environ["J2_BOARD"] = "1"
            j2.RUNS_DIR = "/somewhere/else"
            F.page_file("j2_ui.html")
        before = j2.RUNS_DIR
        F.skippable(block)()
        print("RESTORED", "J2_BOARD" not in os.environ, j2.RUNS_DIR == before)

        def broken():
            raise AssertionError("a real failure is not a skip")
        try:
            F.skippable(broken)()
        except AssertionError as e:
            print("RAISED", e)
        """, tmp_path)
    assert res.returncode == 0, res.stderr[-1500:]
    assert "RESTORED True True" in res.stdout and "RAISED a real failure is not a skip" in res.stdout


def test_the_checkout_variable_names_where_j2_files_are_read(tmp_path):
    fake = tmp_path / "j2"
    fake.mkdir()
    (fake / "j2_ui.html").write_text("<html></html>", encoding="utf-8")
    res = run_python("""
        import os
        import j2_flow_test as F
        print("PAGE", F.HERE == os.environ["SUTRA_J2_CHECKOUT"], F.page_file("j2_ui.html").endswith("j2_ui.html"))
        try:
            F.page_file("j2_graph_layout.js")
        except F.NeedsPage as e:
            print("MISSING", e)
        import j2_replay_size as R
        print("RUN", R.RUN)
        """, tmp_path, SUTRA_J2_CHECKOUT=str(fake))
    assert res.returncode == 0, res.stderr[-1500:]
    assert "PAGE True True" in res.stdout and "MISSING j2_graph_layout.js not found" in res.stdout
    assert f"RUN {fake}/runs/j2-20261015-114723" in res.stdout


def test_replay_size_run_defaults_to_this_folder_without_a_checkout(tmp_path):
    res = run_python("import j2_replay_size as R; print('RUN', R.RUN)", tmp_path)
    assert res.returncode == 0 and f"RUN {LEGACY}/runs/j2-20261015-114723" in res.stdout, res.stderr[-800:]


def test_replay_size_fails_on_a_missing_run_and_writes_nothing(tmp_path):
    res = subprocess.run([sys.executable, str(LEGACY / "j2_replay_size.py"), str(tmp_path / "nope")], cwd=tmp_path, env=clean_env(),
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0 and "calls.jsonl" in res.stderr and not any(tmp_path.iterdir())


def test_the_page_markup_checks_skip_when_the_server_has_no_page(tmp_path):
    res = run_python("""
        import io, urllib.error
        import j2_flow_test as F

        def get(path):
            raise urllib.error.HTTPError(path, 404, "Not Found", {}, io.BytesIO(b""))
        print("PAGE", F.served_page(get))
        print("OK", F.served_page(lambda path: b"<p>x</p>"), F.served_page(lambda path: "<p>y</p>"))

        def boom(path):
            raise urllib.error.HTTPError(path, 500, "x", {}, io.BytesIO(b""))
        try:
            F.served_page(boom)
        except AssertionError as e:
            print("FIVE-HUNDRED", e)
        """, tmp_path)
    assert res.returncode == 0, res.stderr[-1500:]
    assert "PAGE None" in res.stdout and "OK <p>x</p> <p>y</p>" in res.stdout and "FIVE-HUNDRED 500" in res.stdout


def test_generated_screenshot_is_a_valid_png(tmp_path):
    res = run_python(f"""
        import struct, zlib
        import j2_flow_test as F
        F.write_png({str(tmp_path / 's.png')!r}, 8, 5)
        data = open({str(tmp_path / 's.png')!r}, "rb").read()
        assert data[:8] == b"\\x89PNG\\r\\n\\x1a\\n"
        w, h = struct.unpack(">II", data[16:24])
        i, raw = 8, b""
        while i < len(data):
            n = struct.unpack(">I", data[i:i + 4])[0]
            kind = data[i + 4:i + 8]
            assert zlib.crc32(data[i + 4:i + 8 + n]) == struct.unpack(">I", data[i + 8 + n:i + 12 + n])[0]
            raw += data[i + 8:i + 8 + n] if kind == b"IDAT" else b""
            i += 12 + n
        print("PNG", w, h, len(zlib.decompress(raw)))
        """, tmp_path)
    assert res.returncode == 0, res.stderr[-1500:]
    assert "PNG 8 5 125" in res.stdout                      # 5 rows of 1 filter byte + 8 pixels x 3 bytes


def test_blocks_that_need_git_history_are_skipped_with_a_reason(tmp_path):
    res = run_python("""
        import j2_flow_test as F
        F.plain_unchanged("94bffd0", slim="0")
        """, tmp_path)
    assert res.returncode == 0 and "plain brief unchanged: skipped (replaced by the prompt goldens" in res.stdout


def test_demo_flags_refuse_to_write_into_this_repo_without_a_checkout(tmp_path):
    res = run_script(["j2_flow_test.py", "--fast", "--board-demo"], tmp_path)
    assert res.returncode != 0 and "set SUTRA_J2_CHECKOUT" in res.stderr and not any(tmp_path.iterdir())


# ---- scripts/engine_gate.sh --------------------------------------------------------------------------------------------------
def fake_legacy(folder: Path, *, flow_ok_lines=4, flow_exit=0, flow_last="j2 flow checks passed", checks=200, realization=100,
                traceback=False) -> Path:
    """Stand-ins for the three scripts: same names, same output conventions, no J2."""
    folder.mkdir()
    (folder / "EXPECTED.json").write_text(json.dumps({"j2_commit": "x", "flow_fast_ok_lines": 3, "change_checks": 192,
                                                       "realization_checks": 97}), encoding="utf-8")
    flow = "import sys\n" + "print('step ok')\n" * flow_ok_lines + ("print('Traceback (most recent call last):')\n" if traceback else "") + \
        f"print('args', sys.argv[1:])\nprint({flow_last!r})\nsys.exit({flow_exit})\n"
    (folder / "j2_flow_test.py").write_text(flow, encoding="utf-8")
    (folder / "change_test.py").write_text(f"print('change_test: {checks} checks passed')\n", encoding="utf-8")
    (folder / "realization_test.py").write_text(f"print('realization_test: {realization} checks passed')\n", encoding="utf-8")
    return folder


def run_gate(legacy: Path, tmp_path, **env) -> subprocess.CompletedProcess:
    tmp = tmp_path / "tmp"
    tmp.mkdir(exist_ok=True)
    wrapper = tmp_path / "py"
    wrapper.write_text(f'#!/bin/sh\nexec {sys.executable} "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    return subprocess.run(["bash", str(GATE)], cwd=tmp_path, capture_output=True, text=True, timeout=120,
                          env={**clean_env(), "ENGINE_GATE_LEGACY_DIR": str(legacy), "ENGINE_GATE_PY": str(wrapper),
                               "TMPDIR": str(tmp), **env})


def test_gate_script_is_valid_bash_and_executable():
    assert subprocess.run(["bash", "-n", str(GATE)]).returncode == 0
    assert os.access(GATE, os.X_OK)


def test_gate_passes_when_every_script_passes_and_cleans_up(tmp_path):
    res = run_gate(fake_legacy(tmp_path / "legacy"), tmp_path)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "engine gate: ok" in res.stdout and "fast: exit 0, 4 lines ending ' ok'" in res.stdout
    assert "browser:      skipped (set SUTRA_BROWSER=1" in res.stdout
    assert not any((tmp_path / "tmp").iterdir())                      # the throw-away copies are removed on success


@pytest.mark.parametrize("what, kwargs, message", [
    ("flow exit", {"flow_exit": 1}, "fast: exit 1"),
    ("flow last line", {"flow_last": "done"}, "the last line is not 'j2 flow checks passed'"),
    ("too few ok lines", {"flow_ok_lines": 2}, "fewer than 3 lines ending ' ok'"),
    ("a traceback", {"traceback": True}, "a Traceback is in the log"),
    ("too few checks", {"checks": 191}, "below the recorded 192"),
    ("too few realization checks", {"realization": 96}, "below the recorded 97"),
])
def test_gate_fails_on_each_kind_of_red(tmp_path, what, kwargs, message):
    res = run_gate(fake_legacy(tmp_path / "legacy", **kwargs), tmp_path)
    assert res.returncode == 1 and message in res.stdout and "engine gate: FAILED" in res.stdout, (what, res.stdout)
    assert any((tmp_path / "tmp").iterdir())                          # the logs stay for a failed gate


def test_gate_runs_the_scripts_in_separate_copies_not_in_the_source_folder(tmp_path):
    legacy = fake_legacy(tmp_path / "legacy")
    res = run_gate(legacy, tmp_path)
    assert res.returncode == 0 and sorted(p.name for p in legacy.iterdir()) == \
        ["EXPECTED.json", "change_test.py", "j2_flow_test.py", "realization_test.py"]                  # no log, no cache in the source
    assert len(set(re.findall(r"engine-gate-\w+", res.stdout))) == 3                                    # three copies at once


def test_gate_browser_copy_runs_only_when_asked(tmp_path):
    legacy = fake_legacy(tmp_path / "legacy")
    res = run_gate(legacy, tmp_path, SUTRA_BROWSER="1")
    if subprocess.run(["bash", "-c", "command -v node"], capture_output=True).returncode == 0:
        assert res.returncode == 0 and "browser: exit 0" in res.stdout and len(set(re.findall(r"engine-gate-\w+", res.stdout))) == 4
    else:
        assert res.returncode == 0 and "browser:      skipped (node not found)" in res.stdout


def test_gate_needs_expected_json(tmp_path):
    legacy = fake_legacy(tmp_path / "legacy")
    (legacy / "EXPECTED.json").unlink()
    res = run_gate(legacy, tmp_path)
    assert res.returncode == 2 and "EXPECTED.json is missing" in res.stderr
