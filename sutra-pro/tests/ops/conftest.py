"""Fixtures of the ops tests. `sync5_seed` makes the seed library of J2 sync 5 (the one an install had before J2 sync 6, 157 files) the seed
that `doctor.seed_dir()` names, so the tests of the sync-4 and sync-5 rules keep their numbers when the app ships a newer seed. The tests
that prove what a newer seed does to an install (`test_seed_sync_shipped.py`) use the shipped seed and this folder as the install's library."""
from pathlib import Path

import pytest

from sutra_app.ops import doctor

SYNC5_SEED = Path(__file__).parent / "fixtures" / "seed-sync5"


@pytest.fixture
def sync5_seed(monkeypatch) -> Path:
    monkeypatch.setattr(doctor, "seed_dir", lambda: SYNC5_SEED)
    return SYNC5_SEED
