"""The function-node layer of the engine (engine design 4.3a, docs/design/function-nodes.md).

Each function turn is one work atom; an atom closes only through passing checks. This package holds the checks and what
they read, plus (work package E6) the layer that runs them. Nothing here is imported by `engine/__init__.py`.

    registry   the 14 named pure checks, `CheckSpec`, `Outcome`, `REGISTRY` (work package E8)
    evidence   `Evidence`, the bundle a check reads, and the read-only run-folder reader (work package E8)
"""
