"""test_chat_scope.py -- which chats the rail lists is the operator's choice.

The rail was scoped to chats Sutra itself started (owner, 2026-09-09), which on
a machine with 1,181 transcripts and 16 Sutra chats showed 15 rows and hid
1,166 sessions. Both operators are real -- one wants Sutra's own list, one uses
Sutra as the single place to see all their work -- so it is a setting, and
these tests pin the parts that silently break: the default, the validation, the
env override, and that nothing fails closed into an empty rail.
"""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_env():
    """Restore env AND module state after every test in this file.

    These tests point SUTRA_UI_SETTINGS at a tempdir and reload `providers`
    and `app` to pick it up. Without putting both back, the reloaded modules
    keep the tempdir path for the REST of the pytest process -- which is
    exactly what happened: test_app's TestAutomationReader passed alone and
    failed after this file ran. A test that breaks a different file is worse
    than the feature it covers.
    """
    import importlib
    import sys
    saved_env = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved_env)
    for mod in ("providers", "app"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])


def _fresh(tmp, **env):
    """providers bound to an isolated settings file (never the operator's)."""
    import importlib
    import sys
    os.environ["SUTRA_UI_SETTINGS"] = str(Path(tmp) / "settings.json")
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    # RELOAD IN PLACE, never `del sys.modules["providers"]`. Deleting and
    # re-importing builds a NEW module object while org_api (and others) keep a
    # reference to the old one -- so test_app's monkeypatch of
    # providers.load_settings stopped reaching org_api.api_automation, and its
    # TestAutomationReader failed only when this file ran first. reload()
    # mutates the existing object, so every holder sees the change.
    import providers as P
    importlib.reload(P)
    return P


def test_the_default_is_the_owners_scoped_list():
    """The 2026-09-09 decision stays the default. Adding a setting must not
    quietly flip what every other operator already sees."""
    with tempfile.TemporaryDirectory() as tmp:
        P = _fresh(tmp)
        assert P.DEFAULT_CHAT_SCOPE == "sutra"
        assert P.load_settings()["chat_scope"] == "sutra"


def test_the_scope_round_trips():
    with tempfile.TemporaryDirectory() as tmp:
        P = _fresh(tmp)
        assert P.save_settings(chat_scope="all")["chat_scope"] == "all"
        assert P.load_settings()["chat_scope"] == "all"
        assert P.save_settings(chat_scope="sutra")["chat_scope"] == "sutra"


@pytest.mark.parametrize("bad", ["everything", "", "ALL", 1, True, None and "x"])
def test_an_unknown_scope_is_refused_not_stored(bad):
    """Refused with the reason, never silently downgraded -- the operator is
    never told a setting applied when it did not."""
    with tempfile.TemporaryDirectory() as tmp:
        P = _fresh(tmp)
        if bad is None:
            pytest.skip("None means 'not supplied'")
        with pytest.raises(ValueError) as e:
            P.save_settings(chat_scope=bad)
        assert "chat_scope" in str(e.value)
        assert P.load_settings()["chat_scope"] == "sutra", "nothing was written"


def test_a_corrupt_stored_scope_falls_back_and_is_reported():
    """A hand-edited settings file must not empty the rail; the bad value is
    reported in `invalid` rather than swallowed."""
    with tempfile.TemporaryDirectory() as tmp:
        P = _fresh(tmp)
        Path(os.environ["SUTRA_UI_SETTINGS"]).write_text('{"chat_scope": "nonsense"}')
        s = P.load_settings()
        assert s["chat_scope"] == "sutra"
        assert s.get("invalid_stored_values", {}).get("chat_scope") == "nonsense"


def test_the_env_escape_hatch_still_wins():
    """SUTRA_UI_ALL_CHATS=1 predates the setting and is the documented way to
    diagnose without touching stored state, so env must beat the file."""
    import importlib
    import sys
    with tempfile.TemporaryDirectory() as tmp:
        P = _fresh(tmp)
        P.save_settings(chat_scope="sutra")
        os.environ["SUTRA_UI_ALL_CHATS"] = "1"
        try:
            import app as A
            importlib.reload(A)
            assert A._list_every_chat() is True, "env must override a scoped setting"
        finally:
            os.environ.pop("SUTRA_UI_ALL_CHATS", None)


def test_an_unreadable_settings_file_keeps_the_default_rather_than_crashing():
    """_list_every_chat fails soft: the rail must render whatever happens to
    settings.json."""
    import importlib
    import sys
    with tempfile.TemporaryDirectory() as tmp:
        _fresh(tmp)
        Path(os.environ["SUTRA_UI_SETTINGS"]).write_text("{not json")
        import app as A
        importlib.reload(A)
        assert A._list_every_chat() is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
