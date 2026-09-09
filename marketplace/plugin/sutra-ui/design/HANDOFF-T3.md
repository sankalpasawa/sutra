# HANDOFF-T3 — the six audit findings, and the three things left outside them

**written**: 2026-09-10 · **covers**: `seo_agent/research/**`, `seo_agent/write/**`,
`seo_agent/assets/{trends,reuse}.py`, `seo_agent/brand/cta.py`, `seo_agent/foundation/traffic.py`,
`seo_agent/tools/dfs.py`, and the six suites those changes are checked in.

Six findings from the audit of the owner's 223 scripts and 119 prompts against Sutra's port of
them were fixed. Each one is commented where it lives, with the original's file and its real
numbers. This file is only for what could **not** be finished inside those files.

---

## 1. The phrase clustering in study-trends is an ORDERING, not his KMeans

**Where**: `assets/trends.py::_by_meaning`, used by `_candidates`.

His stage 2b (`02-asset-engine/3-study-trends/scripts/step_2b_tensions.py`) does two things with
embeddings, and only one and a half are ported:

| his step | what he uses | ported? |
|---|---|---|
| merge near-identical tension SENTENCES at `MERGE_SIM = 0.85` | agglomerative threshold on cosine | YES — `_settle`, same 0.85 |
| cluster the 1,224 PHRASES into `TARGET_CLUSTERS = 45` groups before naming | **sklearn KMeans** | NO — see below |

He measured the reason for KMeans and wrote it down: a threshold merge on this dense space
"made one 584-phrase mega-cluster whose naming call hung", so he forces a balanced, controlled
cluster count. Repeating a threshold union-find over the phrases would be knowingly re-running a
failure he already recorded.

**sklearn is not a dependency and adding it is not a small decision.** `requirements.txt` is
explicit that the cross-arch DMG installs with `--only-binary`, and pins numpy 2.0.2 for exactly
that reason; sklearn ships compiled wheels and would have to clear the same bar.

**What runs instead**: the phrases are embedded and put in a nearest-neighbour ORDER, and the
existing `CONSOLIDATE_SHARD` (120) cuts that order into calls. Each consolidate call then sees
phrases that mean similar things instead of phrases that were scraped near each other, which is
the part that matters, with no cluster count to tune and no blob to hang on.

**The decision someone still has to make**: is a controlled cluster count worth a compiled
dependency in the bundle? If yes, `_by_meaning` is the one function to replace and
`_meaning_groups` already has the union-find. If no, this is finished and this section is the
record of why.

---

## 2. `llm.py` was touched, and it is not in this lane's file list

**One change**, and finding 2 could not be done anywhere else:

- `_claude_cli_once` turned `subprocess.TimeoutExpired` into a plain `RuntimeError`, and
  `_claude_cli` only retried `ModelError`. So `_TRANSIENT` has listed `"timed out"` and
  `"timeout"` since the day it was written, and a timeout has never once been retried.
- The except clause is now `except RuntimeError` (`ModelError` subclasses it; `NoKey` does not,
  so a sign-in problem still surfaces immediately), and the timeout's message reads
  "The Claude CLI timed out: …" so `_transient()` matches it.

Checked in `tests/test_write.py` ("a CLI call that times out is tried again instead of losing the
step"), driving `llm._claude_cli` directly because that suite runs with `SEO_AGENT_NO_CLI=1`.

**Whoever owns `llm.py`**: this is the only edit, and it is three lines plus comments.

---

## 3. Two test stubs outside this lane grew `**kw`

The planner's model calls now pass a per-call `timeout=` (`llm.call`'s own docstring asks for
"per call, never a global swap"). Two stubs in the tree did not accept keyword arguments and
raised `TypeError`:

- `tests/test_write.py::json_stub` / `text_stub` — this lane's file, fixed.
- `tests/test_picture.py::_stub` — **not this lane's file**. One token, `**kw`, the same signature
  the other nine stubs in the tree already have. No behaviour changed. Flagged here so its owner
  sees it rather than finding it in a diff.

---

## 4. Not a change, a warning for whoever adds the next suite

`brand/cta.rebuild()` now probes every url before it writes `cta-pages.md`, so a suite that runs
`brand/features.run(...)` **will make real network requests** unless it swaps `cta.PROBE`, the way
`tests/test_brand.py` does:

```python
from seo_agent.brand import cta
cta.PROBE = lambda url: (cta.LIVE, "")
```

`example.com` resolves and answers 404 to every invented path, so without the swap the whole list
reads as proven dead. This is the same swap point discipline as `write/_common.ALIVE`.

---

## 5. Red suite that is not this lane's

`tests/test_workspace_core.py` fails one check, **"bucket creation is idempotent"**, on
`seo_agent/workspace/schema.sql`. Nothing here touches `workspace/**` and that suite mentions
none of these files. It was already red when this lane finished; it is the workspace lane's.
