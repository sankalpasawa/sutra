"""Shared test setup. Marked tests need an explicit opt-in so the merge gate stays fast and offline."""
import os
import sys

import pytest

# marker -> the environment variable that switches it on
_OPT_IN = {"live": "SUTRA_LIVE", "slow": "SUTRA_SLOW", "browser": "SUTRA_BROWSER"}


# Tests that cannot run on Windows, by the start of their node id (a file, a class or one test), each with the reason (D104). Every entry is
# something Windows does differently by design, not a bug waiting: a POSIX mode bit, a signal's exit code, a shell script as a program.
WINDOWS_SKIP: dict[str, str] = {}


def pytest_collection_modifyitems(config, items):
    if sys.platform == "win32":
        for item in items:
            for prefix, reason in WINDOWS_SKIP.items():
                if item.nodeid.replace("\\", "/").startswith(prefix):
                    item.add_marker(pytest.mark.skip(reason=reason))
                    break
    for item in items:
        for marker, env in _OPT_IN.items():
            if marker in item.keywords and os.environ.get(env) != "1":
                item.add_marker(pytest.mark.skip(reason=f"set {env}=1 to run {marker} tests"))
