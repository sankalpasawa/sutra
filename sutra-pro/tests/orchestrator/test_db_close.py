"""Database.close waits for the store calls that are still running (found on Windows: closing a connection under a running statement is an
access violation that ends the whole test process, which POSIX happens to survive)."""
import asyncio
import threading
import time

from sutra_app.orchestrator import db as dbmod


def test_close_comes_back_only_after_a_running_store_call_has_ended(db):
    started, finished = threading.Event(), []

    def slow():
        db.conn().execute("SELECT 1").fetchall()
        started.set()
        time.sleep(0.4)
        db.conn().execute("SELECT 2").fetchall()                       # raises if the database was closed under it
        finished.append(time.monotonic())

    async def go():
        await dbmod.run_blocking(slow)

    worker = threading.Thread(target=lambda: asyncio.run(go()))
    worker.start()
    assert started.wait(10)
    db.close()
    assert finished, "close() returned while the store call was still running"
    worker.join(10)
    assert not worker.is_alive()


def test_close_is_immediate_when_nothing_is_running(db):
    began = time.monotonic()
    db.close()
    db.close()
    assert time.monotonic() - began < 1.0


def test_the_counter_returns_to_zero_after_a_call_that_raises(db):
    async def boom():
        await dbmod.run_blocking(lambda: 1 / 0)

    try:
        asyncio.run(boom())
    except ZeroDivisionError:
        pass
    assert dbmod._wait_for_store_calls(0.5) is True
