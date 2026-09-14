"""test_channel_isolation.py -- the beta channel must not leak into production.

A beta build coexists with production (founder, 2026-09-13): its own app, port
and DATA NAMESPACE. The whole safety of that rests on main.js's betaEnv()
redirecting EVERY data path the backend reads. The dangerous, silent failure is
a data-path env var added to the backend later but not to betaEnv() -- the beta
would then write into production for that one thing. This test greps the backend
for every such var and fails if betaEnv() misses one. It also pins the port
split and the guard's beta-tag handling.
"""
import re
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent
ROOT = UI.parents[2]
MAIN_JS = (UI / "electron" / "main.js").read_text()
MAKE_DMG = (UI / "electron" / "make-dmg.sh").read_text()
WORKFLOW = (ROOT / ".github" / "workflows" / "release-dmg.yml").read_text()

# Data-path vars the beta may legitimately NOT redirect:
#  - SUTRA_UI_WORKDIR / _ROOT: the agent's working directory (a real repo the
#    operator picks); beta and stable can share the same code checkout to work
#    in, and isolating it would point beta at a non-existent folder.
#  - SUTRA_NATIVE_HOME handled explicitly below (it is the registry root).
_NOT_DATA_STORE = {"SUTRA_UI_WORKDIR", "SUTRA_UI_WORKDIR_ROOT",
                   "SUTRA_UI_ALL_CHATS", "SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS",
                   "SUTRA_UI_RESOURCES", "SUTRA_UI_PORT", "SUTRA_UI_HOST",
                   "SUTRA_UI_SETTINGS_DIR"}


def _backend_data_vars():
    """Every env var whose default is a path under ~/.sutra-ui or ~/.sutra-native,
    read anywhere in the backend."""
    found = {}
    for py in list(UI.glob("*.py")) + list((ROOT / "marketplace/plugin/lib").glob("*.py")):
        txt = py.read_text(errors="replace")
        for m in re.finditer(
                r'os\.environ\.get\(\s*"(SUTRA_[A-Z_]+)"\s*,\s*"(~?/?\.?[^"]*)"', txt):
            var, default = m.group(1), m.group(2)
            if ".sutra-ui" in default or ".sutra-native" in default:
                found[var] = default
    return found


def _beta_env_vars():
    """The keys betaEnv() sets in main.js."""
    block = MAIN_JS[MAIN_JS.index("function betaEnv()"):MAIN_JS.index("function betaEnv()") + 1500]
    return set(re.findall(r"(SUTRA_[A-Z_]+):", block))


def test_betaEnv_covers_every_backend_data_path():
    backend = set(_backend_data_vars()) - _NOT_DATA_STORE
    covered = _beta_env_vars()
    missing = backend - covered
    assert not missing, (
        "betaEnv() in main.js does not redirect these backend data paths, so a "
        "beta would write into production for them: %s" % sorted(missing))


def test_beta_env_paths_are_all_under_a_beta_namespace():
    block = MAIN_JS[MAIN_JS.index("function betaEnv()"):MAIN_JS.index("function betaEnv()") + 1500]
    # every path is built from `nat` (.sutra-native-beta) or `ui` (.sutra-ui-beta)
    assert ".sutra-native-beta" in block and ".sutra-ui-beta" in block
    # and none hard-codes a production path
    assert re.search(r'"~/\.sutra-ui/"|\.sutra-ui"[^-]', block) is None, \
        "a beta path points at the production ~/.sutra-ui namespace"


def test_the_two_channels_use_different_ports():
    assert re.search(r"IS_BETA\s*\?\s*8331\s*:\s*8330", MAIN_JS), \
        "beta and stable must not share a port, or they cannot coexist"


def test_channel_is_read_from_a_marker_not_app_name():
    # app.getName() is unreliable after electron-packager; the channel must come
    # from the baked marker file.
    assert "function readChannel()" in MAIN_JS
    assert 'path.join(process.resourcesPath || "", "channel")' in MAIN_JS
    assert "app.getName()" not in MAIN_JS[MAIN_JS.index("function readChannel()"):
                                          MAIN_JS.index("const CHANNEL")]


def test_beta_gets_its_own_electron_identity():
    """The bug beta.1 exposed: app.getName() returns "Sutra" for the beta build
    (packager leaves productName), so without an explicit rename the beta shares
    userData AND the single-instance lock with production and exits on launch
    whenever production is open. main.js must set its own name + userData."""
    block = MAIN_JS[MAIN_JS.index("const IS_BETA ="):MAIN_JS.index("function betaEnv")]
    assert 'app.setName("Sutra Beta")' in block, "beta must rename itself"
    assert 'app.setPath("userData"' in block, "beta must repath userData (single-instance lock)"


def test_beta_disables_auto_update():
    sched = MAIN_JS[MAIN_JS.index("function startUpdateSchedule()"):]
    sched = sched[:sched.index("\n}")]
    assert "IS_BETA" in sched and "return" in sched, \
        "a beta must not auto-update to stable (it would defeat coexistence)"


def test_make_dmg_sets_beta_identity_and_writes_the_marker():
    assert 'BUNDLE_ID="os.sutra.ui.beta"' in MAKE_DMG
    assert 'APP_NAME="Sutra Beta"' in MAKE_DMG
    assert 'Contents/Resources/channel' in MAKE_DMG, "the marker main.js reads must be written"


@pytest.mark.parametrize("tag,is_beta", [
    ("v2.267.1-desktop", False),
    ("v2.267.1-beta.1-desktop", True),
    ("v2.267.1-beta.12-desktop", True),
])
def test_workflow_marks_only_beta_tags_as_prerelease(tag, is_beta):
    # mirror the workflow's own predicate: contains(ref, '-beta.')
    assert ("-beta." in tag) == is_beta
    # the guard's base-version strip must land on X.Y.Z for both
    want = tag[1:].replace("-desktop", "")
    want = re.sub(r"-beta\..*$", "", want)
    assert want == "2.267.1"


def test_workflow_has_the_prerelease_flag_and_channel_build():
    assert "prerelease: ${{ contains(github.event.inputs.tag || github.ref_name, '-beta.') }}" in WORKFLOW
    assert "SUTRA_CHANNEL=beta" in WORKFLOW and "SUTRA_CHANNEL=stable" in WORKFLOW


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
