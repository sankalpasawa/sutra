"""The light node host (multi-agent nodes, MAN-11, D256): the process of a node whose runtime is `light`, which today is the reviewer.

    python -m sutra_app.nodes --run-dir <run folder> [--mock]

It makes the same files and events as an engine run (`task.json` in, `events.jsonl` with `run.started`, heartbeats and `run.ended`, `handoff.json` out), so the scheduler, the watcher, the projector,
the lease and the stop ladder treat it as any run. What it does inside is small: read what the steps it checks handed on, ask one model once for a typed verdict, write `verdict.json`. It has no
folder tools, no commands and no network of its own; a model never approves a model: the verdict informs, the owner decides.
"""
