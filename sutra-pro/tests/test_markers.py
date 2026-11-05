"""The opt-in markers skip without their environment variable (the gate never runs live, slow or browser tests)."""
import subprocess
import sys
import textwrap

import pytest


def _run(tmp_path, env_extra):
    (tmp_path / "test_x.py").write_text(textwrap.dedent("""
        import pytest
        @pytest.mark.live
        def test_live(): pass
        @pytest.mark.slow
        def test_slow(): pass
        @pytest.mark.browser
        def test_browser(): pass
        def test_plain(): pass
    """))
    (tmp_path / "conftest.py").write_text(open(__file__.replace("test_markers.py", "conftest.py")).read())
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    live\n    slow\n    browser\n")
    import os
    env = {k: v for k, v in os.environ.items() if not k.startswith("SUTRA_")}
    env.update(env_extra)
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rs", str(tmp_path / "test_x.py")],
                         capture_output=True, text=True, env=env, cwd=tmp_path)
    return out.stdout


def test_marked_tests_skip_by_default(tmp_path):
    out = _run(tmp_path, {})
    assert "1 passed, 3 skipped" in out


@pytest.mark.parametrize("marker,env", [("live", "SUTRA_LIVE"), ("slow", "SUTRA_SLOW"), ("browser", "SUTRA_BROWSER")])
def test_each_marker_runs_with_its_variable(tmp_path, marker, env):
    out = _run(tmp_path, {env: "1"})
    assert "2 passed, 2 skipped" in out
