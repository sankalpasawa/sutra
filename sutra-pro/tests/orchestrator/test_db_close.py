"""Database.close waits for the store calls that are still running (found on Windows: closing a connection under a running statement is an
access violation that ends the whole test process, which POSIX happens to survive)."""
import asyncio
import threading
import time

from sutra_app.orchestrator import db as dbmod


LONG_STATEMENT = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 4000000) SELECT count(*) FROM c"


def test_close_comes_back_only_after_a_running_store_call_has_ended(db):
    started, finished = threading.Event(), []

    def slow():
        db.conn().execute("SELECT 1").fetchall()
        started.set()
        db.conn().execute(LONG_STATEMENT).fetchall()                    # one statement that takes a while inside SQLite
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


def test_a_thread_that_already_has_a_connection_cannot_use_it_once_the_database_is_closing(db):
    """The race that crashed CI: a pooled worker thread keeps its connection between calls, and used to skip the `closed` check."""
    import pytest

    SchemaError = dbmod.SchemaError
    seen = {}

    def first():
        db.conn().execute("SELECT 1").fetchall()                      # this thread now holds a connection of its own

    def second():
        try:
            db.conn().execute("SELECT 2").fetchall()
            seen["second"] = "ran"
        except SchemaError:
            seen["second"] = "refused"

    async def go(fn):
        await dbmod.run_blocking(fn)

    # the same worker thread serves both calls (anyio keeps an idle one around), with the database closed in between
    asyncio.run(go(first))
    db.close()
    asyncio.run(go(second))
    assert seen["second"] == "refused"
    with pytest.raises(SchemaError):
        db.conn()


def test_a_call_whose_event_loop_ended_before_it_did_does_not_leave_the_count_up(db):
    """The leak that made close() wait five seconds and then close under a live statement: a loop that ends with a call pending never runs the
    coroutine's `finally`. The count is kept on the worker thread now, so it returns to zero when the thread's call ends."""
    started = threading.Event()

    def slow():
        db.conn().execute("SELECT 1").fetchall()
        started.set()
        time.sleep(0.3)

    async def go():
        task = asyncio.ensure_future(dbmod.run_blocking(slow))
        await asyncio.sleep(0.05)
        return task                                   # the loop ends here, with the call still pending

    asyncio.run(go())
    assert started.wait(10)
    assert dbmod._wait_for_store_calls(10.0) is True, "the count must come back to zero once the worker thread's call has ended"
