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
electron/ later is still collected."""
collect_ignore = ["seo_agent", "electron/payload", "electron/dist"]
