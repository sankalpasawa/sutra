"""Pytest collection rules for sutra-ui.

The SEO Writer engine (seo_agent/) carries its own checks under seo_agent/tests/. They
are plain scripts: each prints PASS/FAIL lines and calls sys.exit at module level, and
seo_agent/tests/run_all.sh runs them in a throwaway data dir. Pytest importing one of
them at collection time hits that sys.exit and aborts the WHOLE session with an
INTERNALERROR after ~28 tests -- which is how this file came to exist (2026-09-03).

So the engine's own suite is excluded here and run as its own gate step (see
PUBLISH-CHECK.md). The routes that wrap the engine are covered by test_agents_api.py,
which pytest does collect.
"""
collect_ignore = ["seo_agent"]
