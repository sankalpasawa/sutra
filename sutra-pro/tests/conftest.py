"""Shared test setup. Marked tests need an explicit opt-in so the merge gate stays fast and offline."""
import os

import pytest

# marker -> the environment variable that switches it on
_OPT_IN = {"live": "SUTRA_LIVE", "slow": "SUTRA_SLOW", "browser": "SUTRA_BROWSER"}


def pytest_collection_modifyitems(config, items):
    for item in items:
        for marker, env in _OPT_IN.items():
            if marker in item.keywords and os.environ.get(env) != "1":
                item.add_marker(pytest.mark.skip(reason=f"set {env}=1 to run {marker} tests"))
