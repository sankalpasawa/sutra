"""test_perm_mode_default.py -- SAFETY rule 4.

app.py's PERM_MODE must default to something other than "acceptEdits" when
SUTRA_UI_PERMISSION_MODE is unset -- acceptEdits auto-approves the spawned
`claude` subprocess's edits/writes, which is not a safe default for a panel
that (per §8.5.9's own precondition table) already reaches every registry
writer transitively through the chat/term websockets. The env var override
itself must still work (this test does not remove that escape hatch).
"""
import importlib
import os
import sys
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
        os.environ.setdefault(
            "SUTRA_NATIVE_HOME",
            "/private/tmp/claude-501/-Users-tchandrakar-Desktop-development-UI-design-documents-"
            "/fd234fed-a5a8-471b-8052-40a955241b18/scratchpad/dev-registry",
        )
        if "app" in sys.modules:
            del sys.modules["app"]
        if "org_api" in sys.modules:
            del sys.modules["org_api"]
        import app  # noqa: F401 -- imported for its module-level PERM_MODE
        return app
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def test_perm_mode_default_is_not_accept_edits():
    env = {k: v for k, v in os.environ.items() if k != "SUTRA_UI_PERMISSION_MODE"}
    app = _import_app_with_env(env)
    assert app.PERM_MODE != "acceptEdits", (
        "PERM_MODE defaulted to 'acceptEdits' with SUTRA_UI_PERMISSION_MODE "
        "unset -- SAFETY rule 4 requires a safer fallback (e.g. 'plan')."
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
    test_perm_mode_default_is_not_accept_edits()
    test_perm_mode_env_override_still_works()
    print("OK: PERM_MODE default is safe, env override still works")
