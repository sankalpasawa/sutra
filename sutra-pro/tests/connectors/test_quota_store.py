"""The quota snapshot outlives a restart (GAP-providers, quota_store.py): <data>/connectors/quota.json, mode 0600, written on every
change the HealthBook reports, read back at start-up; an exhausted snapshot still blocks until its reset; a bad file is ignored."""
from __future__ import annotations

import json
import logging
import os
import stat
from types import SimpleNamespace

import pytest

from sutra_app.connectors.factory import build_router
from sutra_app.connectors.health import QUOTA_COOLDOWN_S, HealthBook
from sutra_app.connectors.models import ConnectorConfig, Quota, QuotaWindow
from sutra_app.connectors.quota_store import QUOTA_FILE, QuotaStore, attach_quota_store

T0 = 1_000_000.0


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


def snapshot(status="warning", resets_at=T0 + 3600, plan=None):
    return Quota(status=status, window="five_hour", used=0.62, resets_at=resets_at, plan=plan, source="rate_limit_event",
                 windows=[QuotaWindow(key="five_hour", label="5-hour", used=0.62, resets_at=resets_at),
                          QuotaWindow(key="seven_day", label="Weekly", used=0.81, resets_at=T0 + 4 * 86400)])


@pytest.fixture
def path(tmp_path):
    return tmp_path / "data" / "connectors" / QUOTA_FILE


def started(path, now=T0):
    """A HealthBook as the factory leaves it: the stored snapshots loaded, the file kept in step."""
    book = HealthBook(clock=Clock(now))
    attach_quota_store(book, path)
    return book


def test_a_snapshot_is_written_privately_and_read_back_after_a_restart(path):
    book = started(path)
    book.set_quota("claude", snapshot())
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["version"] == 1 and list(stored["providers"]) == ["claude"] and stored["providers"]["claude"]["seen_at"] == T0
    again = started(path, now=T0 + 600)
    quota = again.quota("claude")
    assert quota == book.quota("claude") and quota.seen_at == T0                          # "as of" the time it was seen, not now
    assert [(w.label, w.used) for w in quota.windows] == [("5-hour", 0.62), ("Weekly", 0.81)]


def test_the_book_stamps_when_it_saw_a_snapshot(path):
    book = started(path, now=T0 + 42)
    book.set_quota("codex", snapshot())
    assert book.quota("codex").seen_at == T0 + 42


def test_an_exhausted_snapshot_still_blocks_until_its_reset_after_a_restart(path):
    started(path).set_quota("claude", snapshot(status="exhausted", resets_at=T0 + 5000))
    later = started(path, now=T0 + 2000)
    assert later.state("claude").state == "quota" and later.cooldown("claude").until == T0 + 5000
    assert started(path, now=T0 + 5001).cooldown("claude") is None


def test_an_exhausted_snapshot_without_a_reset_blocks_for_the_cooldown_from_when_it_was_seen(path):
    started(path).set_quota("claude", snapshot(status="exhausted", resets_at=None))
    assert started(path, now=T0 + QUOTA_COOLDOWN_S["claude"] - 1).cooldown("claude") is not None
    assert started(path, now=T0 + QUOTA_COOLDOWN_S["claude"] + 1).cooldown("claude") is None


def test_a_success_that_clears_an_exhausted_snapshot_clears_it_in_the_file_too(path):
    book = started(path)
    book.set_quota("claude", snapshot(status="exhausted"))
    book.set_quota("codex", snapshot(status="ok"))
    book.ok("claude")
    assert list(json.loads(path.read_text(encoding="utf-8"))["providers"]) == ["codex"]
    assert started(path, now=T0 + 10).cooldown("claude") is None


@pytest.mark.parametrize("body", ["{not json", json.dumps({"version": 2, "providers": {}}),
                                  json.dumps({"version": 1, "providers": {"stub": snapshot().model_dump(mode="json")}}),
                                  json.dumps({"version": 1, "providers": {"claude": {"status": "ok", "evil": 1}}}), "[]"])
def test_a_file_that_does_not_read_is_ignored_and_replaced_by_the_next_snapshot(path, body, caplog):
    path.parent.mkdir(parents=True)
    path.write_text(body, encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="sutra_app.connectors.quota_store"):
        book = started(path)
    assert book.quota("claude") is None and "is not used" in caplog.text
    book.set_quota("claude", snapshot())
    assert started(path).quota("claude") is not None


def test_only_claude_and_codex_are_kept(path):
    book = started(path)
    book.set_quota("stub", snapshot())
    assert not path.exists()


def test_a_file_that_cannot_be_written_never_fails_the_snapshot(tmp_path, caplog):
    blocker = tmp_path / "data"
    blocker.write_text("a file where the folder should be", encoding="utf-8")
    book = started(blocker / "connectors" / QUOTA_FILE)
    with caplog.at_level(logging.WARNING, logger="sutra_app.connectors.health"):
        book.set_quota("claude", snapshot())
    assert book.quota("claude").status == "warning" and "quota listener failed" in caplog.text


def test_a_store_holds_figures_only(path):
    QuotaStore(path).save("claude", snapshot(plan="max"))
    text = path.read_text(encoding="utf-8")
    assert "@" not in text and "account" not in text


def test_the_factory_keeps_the_snapshot_and_the_codex_plan_across_a_restart(fake, tmp_path):
    def router():
        cfg = ConnectorConfig(**fake.config_kwargs(tmp_path))
        return build_router(SimpleNamespace(data_dir=cfg.data_dir, connector="auto", offline=False), config=cfg)

    first = router()
    first.health.set_quota("claude", snapshot())
    first.health.set_quota("codex", snapshot(status="ok", plan="plus"))
    first.close()
    second = router()
    try:
        claude, codex = second.provider_summary("claude"), second.provider_summary("codex")
        assert [w.key for w in claude.quota.windows] == ["five_hour", "seven_day"] and claude.quota.seen_at is not None
        assert (codex.plan, codex.plan_label) == ("plus", "ChatGPT Plus")                     # Codex names its plan only in a quota
    finally:
        second.close()
    assert fake.model_calls() == []


def test_an_offline_router_writes_no_quota_file(tmp_path):
    router = build_router(SimpleNamespace(data_dir=tmp_path / "d", connector="stub", offline=False))
    router.health.set_quota("claude", snapshot())
    assert not (tmp_path / "d" / "connectors" / QUOTA_FILE).exists()
