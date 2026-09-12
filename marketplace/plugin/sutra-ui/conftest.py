"""Pytest collection rules for sutra-ui.

The SEO Writer engine (seo_agent/) carries its own checks under seo_agent/tests/. They
are plain scripts: each prints PASS/FAIL lines and calls sys.exit at module level, and
seo_agent/tests/run_all.sh runs them in a throwaway data dir. Pytest importing one of
them at collection time hits that sys.exit and aborts the WHOLE session with an
INTERNALERROR after ~28 tests -- which is how this file came to exist (2026-09-03).

So the engine's own suite is excluded here and run as its own gate step (see
PUBLISH-CHECK.md). The routes that wrap the engine are covered by test_agents_api.py,
which pytest does collect.

BUILD ARTIFACTS ARE EXCLUDED TOO (2026-09-08). bundle-runtime.sh rsyncs the whole
plugin tree into electron/payload/ WITHOUT a test_* exclude (unlike install.sh's
stage), and make-dmg.sh leaves a packaged copy under electron/dist/. Both are
gitignored, so a clean checkout never sees them -- but any machine that has built a
DMG, which is every release machine, ends up with a second test_app.py, test_budget.py
and forty-eight more. Pytest refuses those as duplicate basenames:

    import file mismatch: imported module 'test_app' has this __file__ attribute:
      .../electron/payload/plugin/sutra-ui/test_app.py
    Interrupted: 50 errors during collection

Which means step 4 of PUBLISH-CHECK.md -- the whole backend gate -- could not run at
all on the machine doing the release, while running fine everywhere else. Named
explicitly rather than ignoring electron/ wholesale, so a real Python test added under
electron/ later is still collected.

THE REGISTRY HOME IS REDIRECTED TO A TEMP DIR BEFORE COLLECTION (2026-09-11). On
2026-09-11 a whole-directory pytest run emptied the operator's live registry twice
(holding/research/2026-09-11-registry-reset-rca.md): the first collected test imported
app -> org_api -> placement_engine, which froze the REAL ~/.sutra-native home at import,
so the temp home two later test modules set in setUp() was a no-op and their setUp()
os.remove() ran against the real domain files. The engine now refuses the default home
under pytest (2.264.0), which turns that into an error instead of a deletion -- but only
tests that set their own temp home can still run. This rule gives every test a temp
home at the earliest point pytest offers, before any test module is imported, unless the
operator already pointed SUTRA_NATIVE_HOME somewhere outside ~/.sutra-native or
deliberately set SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS=1. Tests that bind their own temp
home in setUp() keep doing so on top of this; sutra/marketplace/plugin/tests/
temp-root-guard-test.sh checks that this assignment is present."""
import atexit
import os
import shutil
import tempfile

collect_ignore = ["seo_agent", "electron/payload", "electron/dist"]


def _redirect_registry_home_to_temp() -> None:
    if os.environ.get("SUTRA_ALLOW_DEFAULT_HOME_IN_TESTS") == "1":
        return
    real_root = os.path.realpath(os.path.expanduser("~/.sutra-native"))
    current = os.environ.get("SUTRA_NATIVE_HOME", "").strip()
    if current:
        resolved = os.path.realpath(os.path.expanduser(current))
        if resolved != real_root and not resolved.startswith(real_root + os.sep):
            return  # operator-provided temp home: leave it alone
    home = tempfile.mkdtemp(prefix="sutra-ui-pytest-home-")
    os.environ["SUTRA_NATIVE_HOME"] = home
    atexit.register(shutil.rmtree, home, True)


def _redirect_agent_data_to_temp() -> None:
    """The SEO agent's data dir, for the same reason and by the same rule.

    On 2026-09-12 a whole-directory pytest run wrote four chats and two never-finished runs into
    the owner's LIVE company. agents_api calls companies.activate_saved() at import, which pins
    store's data dir to whichever company he had open, and a test setting SEO_AGENT_DATA after
    that import was ignored. store.data_dir() now lets a later value win, which closes that route
    but not this one: a test that UNSETS the variable at teardown (monkeypatch.setenv does exactly
    that) leaves anything still calling data_dir() resolving to ~/.sutra-ui again. Setting it here,
    before collection, means the live folder is never the answer for the whole session.

    An operator already pointing it outside ~/.sutra-ui is left alone, exactly as the rule above
    leaves an operator-provided SUTRA_NATIVE_HOME alone.
    """
    live = os.path.realpath(os.path.expanduser("~/.sutra-ui/agents/seo"))
    current = os.environ.get("SEO_AGENT_DATA", "").strip()
    if current:
        resolved = os.path.realpath(os.path.expanduser(current))
        if resolved != live and not resolved.startswith(live + os.sep):
            return  # caller-provided temp home: theirs, not ours
    home = tempfile.mkdtemp(prefix="sutra-ui-pytest-agent-")
    os.environ["SEO_AGENT_DATA"] = home
    atexit.register(shutil.rmtree, home, True)


_redirect_registry_home_to_temp()
_redirect_agent_data_to_temp()
