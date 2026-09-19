"""test_perm_mode_default.py -- SAFETY rule 4, restated 2026-09-18.

WHAT CHANGED. The shipped default is now Full access
(providers.DEFAULT_PERMISSION_MODE == "bypassPermissions", founder direction:
Setup -> Access and permissions defaults to Full access, not Read only). The
original form of this test -- "PERM_MODE must not be acceptEdits" -- would
still PASS against that default while protecting nothing, which is worse than
no test: bypassPermissions is strictly wider than the mode it was written to
forbid. So the assertion is rewritten to the contract that is actually load
bearing now.

WHAT SAFETY RULE 4 RESTS ON INSTEAD. Not this constant being narrow, but:

  1. the unsafe-mode CONSENT GATE (providers.unsafe_modes_allowed) -- an
     unsafe default is clamped to providers.PERMISSION_MODE_FLOOR at the point
     of USE until the operator has acknowledged it in the UI or the server was
     started with SUTRA_UI_ALLOW_UNSAFE_PERM_MODES=1. Widening the default did
     not widen the gate; test_access_options and test_ws_origin_guard cover it.
  2. PERMISSION_MODE_FLOOR staying `plan`, so every narrowing path (the clamp,
     the Shadow autonomy ceiling, an unparseable stored value) still lands on
     read-only rather than on the new default.

WHAT THIS FILE STILL GUARDS. That PERM_MODE has ONE source of truth -- it
mirrors providers.DEFAULT_PERMISSION_MODE rather than a literal, so the two
can never drift into disagreeing about what the shipped default is -- and that
the SUTRA_UI_PERMISSION_MODE escape hatch still works.
"""
import importlib
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _import_app_with_env(monkeypatch_env):
    """Import (or re-import) app.py with a controlled environment so the
    module-level `PERM_MODE = os.environ.get(...)` line re-evaluates."""
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    old_env = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(monkeypatch_env)
        # SUTRA_NATIVE_HOME must be set before org_api (imported by app.py)
        # runs its module-level guard, or it silently defaults to the dev
        # fixture -- fine for this test's purposes, but keep it explicit and
        # never pointed at the real ~/.sutra-native by accident.
        os.environ.setdefault("SUTRA_NATIVE_HOME", tempfile.mkdtemp(prefix="sutra-ui-test-"))
        if "app" in sys.modules:
            del sys.modules["app"]
        if "org_api" in sys.modules:
            del sys.modules["org_api"]
        import app  # noqa: F401 -- imported for its module-level PERM_MODE
        return app
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_perm_mode_default_tracks_the_one_shipped_default():
    """PERM_MODE must not restate a literal of its own."""
    env = {k: v for k, v in os.environ.items() if k != "SUTRA_UI_PERMISSION_MODE"}
    app = _import_app_with_env(env)
    import providers
    assert app.PERM_MODE == providers.DEFAULT_PERMISSION_MODE, (
        "PERM_MODE (%r) has drifted from providers.DEFAULT_PERMISSION_MODE "
        "(%r) -- the shipped default has one home, and two copies of it will "
        "disagree the next time one is changed."
        % (app.PERM_MODE, providers.DEFAULT_PERMISSION_MODE)
    )


def test_the_floor_is_still_read_only_whatever_the_default_is():
    """The half of SAFETY rule 4 that survived the default being widened.

    Everything that NARROWS a mode lands on PERMISSION_MODE_FLOOR. If that
    ever becomes an unsafe mode, the unsafe-mode clamp and the Shadow autonomy
    ceiling both silently stop narrowing anything.
    """
    env = {k: v for k, v in os.environ.items() if k != "SUTRA_UI_PERMISSION_MODE"}
    _import_app_with_env(env)
    import providers
    assert providers.PERMISSION_MODE_FLOOR == "plan", (
        "PERMISSION_MODE_FLOOR is %r, not 'plan' -- the clamp floor must stay "
        "the narrowest mode in PERMISSION_MODES."
        % (providers.PERMISSION_MODE_FLOOR,)
    )
    assert providers.PERMISSION_MODE_FLOOR not in providers.UNSAFE_PERMISSION_MODES, (
        "the clamp floor is itself an unsafe mode -- clamping down is now a "
        "no-op."
    )


def test_perm_mode_env_override_still_works():
    env = dict(os.environ)
    env["SUTRA_UI_PERMISSION_MODE"] = "acceptEdits"
    app = _import_app_with_env(env)
    assert app.PERM_MODE == "acceptEdits", (
        "explicit SUTRA_UI_PERMISSION_MODE override was not honored -- the "
        "fallback change must not remove the env var escape hatch."
    )


if __name__ == "__main__":
    test_perm_mode_default_tracks_the_one_shipped_default()
    test_the_floor_is_still_read_only_whatever_the_default_is()
    test_perm_mode_env_override_still_works()
    print("OK: PERM_MODE tracks the one shipped default, the clamp floor is "
          "still read-only, env override still works")
