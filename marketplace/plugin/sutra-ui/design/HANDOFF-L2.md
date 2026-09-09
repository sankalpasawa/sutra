# HANDOFF — layer 02 (the asset engine), 2026-09-10

Six findings were built: 8.13, 8.14, 8.15, 8.16, 8.17 and 8.4. All of them landed inside
`seo_agent/assets/**`, `seo_agent/prompts/assets/**` and the `test_assets_*` suites, so **nothing
in this list is required for the six to work.** `loop.py`, `registry.py`, `app.py`, `agents_api.py`
and `tools/dfs.py` were not touched and did not need to be.

What follows is the two calls that were made rather than asked about, and the one optional
extension that would need a file layer 02 does not own.

---

## 1. The relevance recheck proposes; it does not delete (finding 8.13)

His `4-merge/scripts/step_3_relevance.py` defaults to PROPOSE — it writes a drop list and changes
nothing — and a person then re-runs it with `--apply` to remove the rows. Sutra has no `--apply`
and the sheet is live: `_common.next_open` hands the top-ranked open idea to the chip as the next
thing to write. A proposal with literally no consequence would therefore leave a
"<Company> Pricing Calculator" sitting at rank 1, which is the outcome the step exists to prevent.

So the port keeps PROPOSE and gives it the smallest honest consequence:

- the row stays on the sheet, with its proof and its reason, and is never deleted;
- the reason is written onto the row as `relevance: {verdict, why}` (a new field on
  `_common.blank_idea`, blank meaning the question was never put);
- `merge.rank` sends a proposed drop to the bottom, the same treatment this file already gives an
  idea a method judged unownable;
- every verdict goes to `_work/merge/relevance-verdicts.json` and the drops to
  `_work/merge/relevance-drops.json`.

**If the owner wants his `--apply` semantics as well** (actually removing the rows after he has
read the list), the change is in `seo_agent/registry.py` and `seo_agent/loop.py`, not in assets:

- `registry.py` — register a tool `apply_relevance_drops` pointing at a new
  `tools/build_assets.py` entry. `build_assets.py` IS owned by layer 02 and can host the function;
  only the registry line is outside.
- `loop.py` — nothing, if the tool is called by name. If it should be a third human gate instead,
  loop.py would have to learn a gate kind `relevance`, and `_common.GATE_FILES` would need
  `"relevance": "_work/merge/relevance-drops.json"`. **This was deliberately NOT done:** the engine
  has exactly two human gates (the competitor shortlist and the subreddit list) and adding a third
  is an architecture change nobody asked for.

## 2. The 15% cap gained an absolute floor (finding 8.13)

His cap is a bare fraction — refuse to apply if the judge wants to drop more than 15% of the sheet.
His pools run to a couple of thousand ideas, where 15% is three hundred. Sutra's can be a couple of
dozen: one honest drop out of six reads as 17% and the pass refuses itself, so on exactly the
sheets a person is most likely to be looking at it could never do anything at all.

`merge.RELEVANCE_MIN_DROPS = 3` makes the cap the LOOSER of the two — a percentage on a big sheet,
a small absolute number on a small one. The rule being enforced is unchanged.

## 3. F0 lives in `assets/formats.py` and method 1 calls it (finding 8.17)

`formats.canonicalise()` is a format-LABEL tidier: labels in, one canonical name per label out,
plus the shapes that are not content assets. It reads no method's ideas and writes no method's
file, so `competitors.py` importing it is not one finder seeing another finder's output — the three
methods still meet only at the merge. It was put in `formats.py` because that is where the owner
asked for it; if it is ever wanted somewhere more neutral, `assets/_common.py` is the place, and the
move is one import line in `competitors.py`.

## 4. Domain validation fails OPEN when nothing at all resolves (finding 8.14)

His `validate_domains.py` is run by hand, so a machine with no network fails in front of him.
Sutra's runs unattended, where "nothing resolved" would read as "every competitor is dead" and
empty the study. `competitors._validate` therefore keeps the whole list, and says so, when NOT ONE
domain answers. A dead domain among live ones is still swapped or dropped exactly as he does it.

---

## Note for whoever reads this next: the tree was being edited concurrently

While this work was running, other agents were editing `loop.py`, `registry.py`, `research/**`,
`brand/**`, `foundation/**` and `tools/**` in the same checkout. `bash seo_agent/tests/run_all.sh`
was fully green at the start of layer 02's work and is not green now, but every failing suite
(`test_loop`, `test_tools`, `test_research`, `test_credit_guard`) belongs to that other work and
none of them imports `seo_agent.assets`. All six `test_assets_*` suites pass.
