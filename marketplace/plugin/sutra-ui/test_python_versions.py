"""test_python_versions.py -- one supported Python range, in every build.

The pins need Python 3.11-3.12 (cryptography's only wheel is cp311-abi3; numpy
2.0.2 has no cp313 wheel). Three places choose an interpreter and drifted apart:
the release DMG bundled 3.12, while install.sh and run.sh ran a bare `python3`
-- Xcode's 3.9 on a stock Mac -- and died inside `pip install` on every default
machine. These tests pin the three to one range, and run install.sh's REAL
selection code against fake interpreters so the rule is exercised, not just
grepped.
"""
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
INSTALL = (HERE / "install.sh").read_text()
RUN = (HERE / "run.sh").read_text()
BUNDLE = (HERE / "electron" / "bundle-runtime.sh").read_text()
REQS = (HERE / "requirements.txt").read_text()


def _ver(s):
    return tuple(int(x) for x in s.split("."))


def _install_range():
    lo = re.search(r'^SUTRA_PY_MIN="([\d.]+)"', INSTALL, re.M).group(1)
    hi = re.search(r'^SUTRA_PY_MAX="([\d.]+)"', INSTALL, re.M).group(1)
    return _ver(lo), _ver(hi)


# ---------------------------------------------------------------- agreement ---

def test_the_release_bundle_is_inside_the_supported_range():
    """The DMG's interpreter and the dev install must accept the same Pythons,
    or a pin that installs in one build breaks the other."""
    lo, hi = _install_range()
    bundled = re.search(r'PY_VERSION="\$\{SUTRA_PY_VERSION:-([\d.]+)\}"', BUNDLE).group(1)
    assert lo <= _ver(bundled)[:2] <= hi, \
        "bundle-runtime.sh ships %s, install.sh accepts %s-%s" % (bundled, lo, hi)


def test_run_sh_uses_the_same_range_as_install_sh():
    lo, hi = _install_range()
    m = re.search(r"\((\d+),(\d+)\) <= sys\.version_info\[:2\] <= \((\d+),(\d+)\)", RUN)
    assert re.search(r'-x "\.venv/bin/python" \] && in_range', RUN), \
        "run.sh must range-check the checkout .venv, not trust it"
    assert m, "run.sh must range-check its interpreter"
    assert (int(m.group(1)), int(m.group(2))) == lo
    assert (int(m.group(3)), int(m.group(4))) == hi


def test_no_build_creates_a_venv_with_a_bare_python3():
    """`python3 -m venv` is how the 3.9 interpreter got in."""
    assert not re.search(r"^\s*python3 -m venv", INSTALL, re.M)
    assert 'PY="python3"' not in RUN


def test_requirements_no_longer_claims_the_pins_run_on_3_9():
    assert "still runs on the\n# dev venv's Python 3.9" not in REQS
    assert "3.11-3.12" in REQS, "the supported range must be written beside the pins"


# ---------------------------------------------------- install.sh's selection ---

def _selection_block():
    """install.sh's real range check + finder, cut out verbatim."""
    start = INSTALL.index('SUTRA_PY_MIN="')
    end = INSTALL.index('if [ "${1:-}" != "--uninstall" ]; then', start)
    return INSTALL[start:end]


def _fake(tmp, name, in_range):
    """An executable that answers py_in_range's probe with a fixed verdict."""
    p = Path(tmp) / name
    p.write_text("#!/bin/sh\nexit %d\n" % (0 if in_range else 1))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def _find(available, sutra_python=None):
    """Run install.sh's find_python with only `available` on the machine.

    `command` is shadowed so the absolute Homebrew probes cannot leak the real
    interpreters on whatever machine runs the suite."""
    with tempfile.TemporaryDirectory() as tmp:
        table = {name: _fake(tmp, name.replace("/", "_"), ok)
                 for name, ok in available.items()}
        cases = "\n".join('    "%s") echo "%s"; return 0;;' % (n, p) for n, p in table.items())
        script = _selection_block() + '''
command() {
  if [ "$1" = "-v" ]; then
    case "$2" in
%s
      *) return 1;;
    esac
  fi
  builtin command "$@"
}
find_python
''' % cases
        env = dict(os.environ)
        env.pop("SUTRA_PYTHON", None)
        if sutra_python:
            env["SUTRA_PYTHON"] = sutra_python
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env)
        picked = r.stdout.strip()
        inv = {p: n for n, p in table.items()}
        return r.returncode, inv.get(picked, picked)


def test_prefers_3_12_the_version_the_release_ships():
    code, picked = _find({"python3.12": True, "python3.11": True, "python3": False})
    assert (code, picked) == (0, "python3.12")


def test_falls_back_to_3_11_when_3_12_is_absent():
    """The founder's machine: Homebrew has 3.11 and 3.13, python3 is 3.9."""
    code, picked = _find({"python3.11": True, "python3": False})
    assert (code, picked) == (0, "python3.11")


def test_refuses_3_13_and_the_stock_3_9():
    """Out-of-range interpreters are never chosen, even when they are all there is."""
    code, picked = _find({"python3.13": False, "python3": False})
    assert code != 0 and picked == ""


def test_a_bare_python3_is_used_only_when_it_is_itself_in_range():
    code, picked = _find({"python3": True})
    assert (code, picked) == (0, "python3")


def test_sutra_python_wins_when_it_is_in_range():
    code, picked = _find({"/custom/py": True, "python3.12": True}, sutra_python="/custom/py")
    assert (code, picked) == (0, "/custom/py")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
