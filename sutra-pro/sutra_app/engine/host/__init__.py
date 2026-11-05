"""The engine process (work package E3, engine design 4.5 to 4.7).

    loop.py        `main()`: reads `task.json`, sets the environment, builds the model port and the hooks, starts J2's run and
                   ends it with `run.ended`
    inbox.py       the tailer of `inbox.jsonl` and the FIFO with its delivery rule
    publisher.py   `StatePublisher`: `snapshot.json`, `live.json` and the node, step and atom/1 events
    heartbeat.py   the heartbeat thread

This package imports nothing of J2 at import time (`engine.j2` reads the environment when it is imported, so `loop.main`
sets the environment first and imports J2 and the publisher afterwards).
"""
