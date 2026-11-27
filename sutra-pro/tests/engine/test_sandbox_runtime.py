"""The bundled srt (D462): which srt J2 launches (`llm.sandbox_cmd`), the sandbox status, and failing closed when the bundle can't start."""
import logging
import shlex
import subprocess
import sys

import pytest

from sutra_app.engine import llm


def fake_node(folder, version):
    """A python script that answers `-p process.versions.node` like node does."""
    p = folder / "node"
    p.write_text(f"#!{sys.executable}\nimport sys\nif sys.argv[1:] == ['-p', 'process.versions.node']:\n    print({version!r})\n")
    p.chmod(0o755)
    return p


@pytest.fixture
def live(monkeypatch, tmp_path):
    """darwin, live, J2_SANDBOX and J2_SANDBOX_CMD unset, PATH = only a fake-node folder, the node probe's cache empty."""
    for name in ("J2_SANDBOX", "J2_SANDBOX_CMD", "SUTRA_ELECTRON_NODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm.sys, "platform", "darwin")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    monkeypatch.setenv("PATH", str(bin_))
    llm._node_version.cache_clear()
    yield bin_
    llm._node_version.cache_clear()


@pytest.mark.parametrize("version", ["22.12.0", "24.22.1"])
def test_a_new_enough_node_runs_the_bundled_srt(live, version):
    node = fake_node(live, version)
    on, why = llm.sandbox_status(mock=False)
    assert on and why == f"bundled srt 0.0.83 at {llm.SRT_DIR}, node {version}"
    assert shlex.split(llm.sandbox_cmd()) == [str(node), str(llm.SRT_DIR / "srt.mjs")]


def test_an_old_node_keeps_the_sandbox_on_and_says_why(live):
    node = fake_node(live, "20.0.0")
    on, why = llm.sandbox_status(mock=False)
    assert on and "needs node >= 22.12 (found 20.0.0" in why and str(node) in why


def test_no_node_keeps_the_sandbox_on_and_says_why(live):
    on, why = llm.sandbox_status(mock=False)
    assert on and "no node on PATH" in why


def test_a_missing_bundle_keeps_the_sandbox_on_and_every_launch_is_refused(live, monkeypatch, tmp_path):
    """AC-6: on with the bundled folder in the reason; the command stands in for srt, prints why and exits 1."""
    fake_node(live, "24.22.1")
    empty = tmp_path / "no-bundle"
    empty.mkdir()
    monkeypatch.setattr(llm, "SRT_DIR", empty)
    on, why = llm.sandbox_status(mock=False)
    assert on and str(empty) in why
    argv = shlex.split(llm.sandbox_cmd())
    assert argv[:2] == [sys.executable, "-c"]
    done = subprocess.run(argv + ["-s", "x", "-c", "touch should-not-exist"], capture_output=True, text=True, cwd=tmp_path, timeout=30)
    assert done.returncode == 1 and str(empty) in done.stderr and "Restore it" in done.stderr
    assert not (tmp_path / "should-not-exist").exists()


def test_off_only_for_j2_sandbox_0_offline_and_windows(live, monkeypatch):
    fake_node(live, "24.22.1")
    assert llm.sandbox_status(mock=True)[0] is False
    monkeypatch.setenv("J2_SANDBOX", "0")
    assert llm.sandbox_status(mock=False) == (False, "J2_SANDBOX=0")
    monkeypatch.delenv("J2_SANDBOX")
    monkeypatch.setattr(llm.sys, "platform", "win32")
    assert llm.sandbox_status(mock=False)[0] is False


def test_the_app_runs_srt_on_electrons_node(live, tmp_path, monkeypatch):
    """AC-16, first part: SUTRA_ELECTRON_NODE puts `env ELECTRON_RUN_AS_NODE=1 <exe> <bundle>/srt.mjs` first."""
    exe = fake_node(tmp_path, "24.22.1")
    monkeypatch.setenv("SUTRA_ELECTRON_NODE", str(exe))
    assert shlex.split(llm.sandbox_cmd()) == ["env", "ELECTRON_RUN_AS_NODE=1", str(exe), str(llm.SRT_DIR / "srt.mjs")]
    assert llm.sandbox_status(mock=False) == (True, f"bundled srt 0.0.83 at {llm.SRT_DIR}, node 24.22.1")


def test_the_override_warns_on_every_launch(live, tmp_path, monkeypatch, caplog):
    """AC-15 (unit): one WARNING per sandbox_cmd() call naming the override's resolved path."""
    srt = live / "my-srt"
    srt.write_text("#!/bin/sh\n")
    srt.chmod(0o755)
    monkeypatch.setenv("J2_SANDBOX_CMD", "my-srt --debug")
    caplog.set_level(logging.WARNING, logger="sutra_app.engine.llm")
    for n in (1, 2):
        assert llm.sandbox_cmd() == "my-srt --debug"
        warnings = [r for r in caplog.records if r.name == "sutra_app.engine.llm" and r.levelno == logging.WARNING]
        assert len(warnings) == n and str(srt) in warnings[-1].getMessage()
    assert llm.sandbox_status(mock=False) == (True, f"J2_SANDBOX_CMD overrides the bundled srt: my-srt at {srt}")


def test_the_command_is_never_empty(live, monkeypatch, tmp_path):
    assert llm.sandbox_cmd()                     # no node
    fake_node(live, "20.0.0")
    llm._node_version.cache_clear()
    assert llm.sandbox_cmd()                     # old node
    monkeypatch.setattr(llm, "SRT_DIR", tmp_path / "gone")
    assert llm.sandbox_cmd()                     # no bundle
