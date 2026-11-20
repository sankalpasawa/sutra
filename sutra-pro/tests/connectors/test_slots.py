"""Machine-wide provider slots (MAN-12): two pools over one folder never hold more than the limit, a waiter gets a slot the moment one is released, a process that dies frees its slot, and the router
takes a slot around each call only when it has a pool."""
import multiprocessing
import os
import threading
import time

import pytest

from sutra_app.connectors.slots import SlotPool


def hold(directory, provider, seconds, ready):
    pool = SlotPool(directory, {"claude": 2, "codex": 1})
    slot = pool.acquire(provider, timeout=5)
    ready.put(slot.index if slot else None)
    time.sleep(seconds)


def test_the_limit_holds_across_pools_and_a_release_gives_the_slot_to_a_waiter(tmp_path):
    first, second = SlotPool(tmp_path / "s", {"claude": 2}), SlotPool(tmp_path / "s", {"claude": 2})        # two routers (two processes) over one folder
    a, b = first.acquire("claude", timeout=1), second.acquire("claude", timeout=1)
    assert {a.index, b.index} == {0, 1} and first.in_use("claude") == 2
    assert first.acquire("claude", timeout=0.2) is None and second.acquire("claude", timeout=0.2) is None            # the third waits and gives up
    got = []
    waiter = threading.Thread(target=lambda: got.append(second.acquire("claude", timeout=3)))
    waiter.start()
    time.sleep(0.2)
    first.release(a)
    waiter.join(5)
    assert got and got[0] is not None and first.in_use("claude") == 2
    second.release(got[0])
    second.release(b)
    assert first.in_use("claude") == 0


def test_a_wait_ends_when_the_request_is_cancelled(tmp_path):
    pool = SlotPool(tmp_path / "s", {"codex": 1})
    held = pool.acquire("codex", timeout=1)
    stop = threading.Event()
    threading.Timer(0.2, stop.set).start()
    started = time.monotonic()
    assert pool.acquire("codex", timeout=10, cancelled=stop.is_set) is None and time.monotonic() - started < 3
    pool.release(held)


@pytest.mark.skipif(os.name == "nt", reason="the child process of this test uses fork")
def test_a_process_that_dies_frees_its_slot(tmp_path):
    ctx = multiprocessing.get_context("fork")
    ready = ctx.Queue()
    child = ctx.Process(target=hold, args=(str(tmp_path / "s"), "codex", 30, ready))
    child.start()
    assert ready.get(timeout=5) == 0
    pool = SlotPool(tmp_path / "s", {"codex": 1})
    assert pool.acquire("codex", timeout=0.2) is None and pool.in_use("codex") == 1                  # the child holds the only slot
    child.kill()
    child.join(5)
    slot = pool.acquire("codex", timeout=3)
    assert slot is not None                                                                         # the kernel let go of the dead process's lock
    pool.release(slot)


def test_the_router_takes_a_slot_around_a_call_only_with_a_pool(tmp_path):
    from test_node_identity import Rig
    rig = Rig(tmp_path)
    seen = []

    class Spy:
        def acquire(self, provider, **kw):
            seen.append(("acquire", provider))
            return object()

        def release(self, slot):
            seen.append(("release",))
    rig.call()
    assert seen == []                                                                                # no pool, no slot
    rig.router.slots = Spy()
    rig.call()
    assert [s[0] for s in seen] == ["acquire", "release"] and seen[0][1] in ("claude", "codex")
    class Full:
        def acquire(self, provider, **kw):
            return None
        def release(self, slot):
            raise AssertionError("nothing was taken")
    rig.router.slots = Full()
    from sutra_app.connectors.errors import ConnectorError
    with pytest.raises(ConnectorError):
        rig.call()                                                                                   # no slot in time: the call is refused as busy, nothing was left held
