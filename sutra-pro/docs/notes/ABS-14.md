# ABS-14 as built

`docs/MIGRATING-FROM-SUTRA.md`: what moved, where it lives, how to import old chats, what Sutra Pro already did differently, what was left behind and why, and what is not done yet (written from the design and the as-built notes of ABS-0 to ABS-13, so the "not done" list is the real one). The chassis documents (DESIGN.md, TRACEABILITY.md) were not touched; `OPERATIONS.md` gained the `import-old-chats` command only because `scripts/check_docs.py` requires every command to be documented (ABS-12). `scripts/check_docs.py` and `tests/test_docs.py` pass.
