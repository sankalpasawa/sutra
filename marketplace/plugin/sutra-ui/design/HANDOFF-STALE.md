# HANDOFF — paths written before the thing that supersedes them, 2026-09-10

The SEO Writer grew an asset engine (~1,900 ranked ideas), a write phase and a team workspace in
two days. Several older paths were written before those existed and still behave as if they do not.
This is the sweep. Everything in `registry.py`, `tools/suggest_topics.py`, `tools/build_assets.py`,
`prompts/suggest_topics.md`, `tests/test_tools.py` and `tests/test_endtoend.py` was FIXED in place
and is listed at the bottom for the record.

Everything below is in a file this job does not own, so it is written out exactly. Ordered worst
first: the first one is a 500 on a live screen.

---

## 1. `GET /assets` throws the moment the asset engine runs its own merge — `agents_api.py:1955`

**Two writers, two shapes, one reader.** `_work/merge/methods.json` is written by two different
places with two different shapes, and the reader was written for one of them:

| Writer | Line | `methods` is |
|---|---|---|
| `seo_agent/assets/import_sheet.py` | 143-144 | a **dict**: `{m: "ran" for m in report["methods"]}` |
| `seo_agent/assets/merge.py` | 117, 130 | a **list**: `[{"method":…, "file":…, "state":…, "ideas":…}, …]` |

`agents_api.py:1955-1958` reads it as the dict:

```python
    m = acm.read("_work/merge/methods.json") or {}
    states = m.get("methods") or {}
    ran = sorted([k for k, v in states.items() if v == "ran"]) or \
        sorted({x for r in rows for x in (r.get("method") or [])})
```

Proved, not guessed. With a merge-written `methods.json` on disk:

```
>>> agents_api._assets_payload()
AttributeError: 'list' object has no attribute 'items'
```

That is `GET /assets` and `POST /assets/{id}/status` (which returns `_assets_payload()` too), so
the whole Asset ideas tab 500s. It has not bitten yet only because the sheet in the owner's install
was **imported**, and the import path writes the dict. The first `build_assets` run that reaches
the merge breaks the tab.

**The fix, in `agents_api.py`, `_assets_payload`.** Normalise both shapes at the one reader.
Replace lines 1955-1958 (`m = acm.read(...)` through the two-line `ran = ...`) with:

```python
    m = acm.read("_work/merge/methods.json") or {}
    # TWO WRITERS, TWO SHAPES. assets/merge.py writes a LIST of {method, file, state, ideas};
    # assets/import_sheet.py writes a DICT of {method: state}. Normalise here rather than at the
    # two writers, because the list carries the per-method detail _methods_line() needs and the
    # dict is what this screen wants. (Found 2026-09-10: the list form raised AttributeError and
    # took the whole Asset ideas tab down with it.)
    raw = m.get("methods") or {}
    states = ({r.get("method"): r.get("state") for r in raw if isinstance(r, dict)}
              if isinstance(raw, list) else raw)
    ran = sorted([k for k, v in states.items() if v == "ran"]) or \
        sorted({x for r in rows for x in (r.get("method") or [])})
```

Everything below it (`"methods": states`, `"methods_blocked": [...]`) then works unchanged.

**Then add the check** that would have caught it, in `seo_agent/tests/test_assets_merge.py`
(a file layer 02 owns): after the merge writes its record, feed that real record to
`_assets_payload()` and assert it comes back with `methods_run` naming the methods that ran. A test
that only reads `methods.json` back with `cm.read` cannot see this: both shapes read back fine, and
only the consumer disagrees.

---

## 2. The opening screen still offers the pre-asset-engine starter — `static/js/17-agents.js:614-616`

This is the instance the owner hit. `agHeroHtml` draws two starter chips for a set-up install:

```js
  const plays = ready ? [
    ["Suggest six topics we could own", "Studies one competitor's best pages and proposes six topics with an angle they have not taken.",
     "Suggest six topics we could own."],
```

`ready` is `agSetupOf(health).ready`, which knows about the catalogue, the page index and the brand
pack. It does not know about the asset sheet, because **`/health` does not report it**
(`agents_api.py:2044-2069` (`api_health`) returns `site_indexed`, `page_index`, `brand_ready` and nothing about
`assets`). So a person with 1,890 ranked ideas, each already judged for ownability and linkability,
is offered six fresh competitor-derived guesses as the first move.

`registry.py` and `tools/suggest_topics.py` are now fixed so the model and the tool both refuse
this. The chip still asks for it in so many words, and a person clicking a chip is not the model
choosing a tool. It needs both halves:

**(a) `agents_api.py`, `api_health()`.** Add one key beside `brand_ready`:

```python
    try:
        from seo_agent.tools import build_assets as _ba
        assets = _ba.status()          # {built, total, counts, methods_run, next}
    except Exception:  # noqa: BLE001 — health must answer even when the sheet cannot be read
        assets = {"built": False, "next": None}
```
and in the returned dict:
```python
            "assets": {"built": bool(assets.get("built")),
                       "open": (assets.get("counts") or {}).get("open", 0),
                       "next": assets.get("next")},
```

**(b) `static/js/17-agents.js`, `agHeroHtml`.** Pick the first play off the sheet when there is one:

```js
  const nx = health && health.assets && health.assets.next;
  const plays = ready ? [
    nx
      ? ["Write the next idea on the sheet",
         "Top of the " + agNum((health.assets.open || 0)) + " still to write, already ranked for whether you can own it and whether anyone would cite it: " + nx.title,
         "Write this asset idea: " + nx.title]
      : ["Suggest six topics we could own",
         "No asset sheet yet, so this studies one competitor's best pages and proposes six topics with an angle they have not taken.",
         "Suggest six topics we could own."],
    ["Write an article about a topic I name", …unchanged…],
  ] : [ …unchanged… ];
```

Note the chip on the Asset ideas tab (`agAssetsHtml`, line ~1911) already carries `data-arg="<id>"`
so the id reaches `store.patch_state(..., idea_id=...)`. A hero chip built from `next` should carry
the same `data-arg`, or the provenance tick in `loop._save_to_library` never fires for it.

**One test moves with it.** `test_agents.js:512` asserts `/Suggest six topics/` for a set-up
install, on a health payload with no `assets` key:

```js
  assert.ok(/Suggest six topics/.test(ok), "a set-up site offers the article plays");
```

That stays correct as the NO-SHEET case (health without `assets` means no sheet), so the assertion
does not have to change. Add a second one beside it with `assets: {built: true, open: 1890, next:
{id: "a0042", title: "Cost of a bad hire, benchmarked"}}` and assert the hero offers that idea
instead. `system.md` (rewritten 2026-09-10) already says this in words for the model: *"NEVER ask a
person to think of a topic while the sheet is holding one."* The chip is the same rule on screen.

---

## 3. `run_research` never reads `idea_id`, and a comment says it does — `agents_api.py:191-197`

```python
    # The chip on the Asset ideas tab carries the idea's id as DATA, not as words in the message.
    # … Research reads it to get the angle; the Library save reads it to tick the idea. The model
    # touches it at no point.
```

`grep -n idea seo_agent/tools/run_research.py` returns **nothing**. Only the Library save reads it
(`loop.py:766-792`). So the angle, the format and the linkability score the asset engine already
worked out for that idea are thrown away, and `run_research` re-derives an angle from scratch on a
topic that was chosen precisely because its angle had been judged.

Two things, and they are separable:

**(a) Correct the comment now** (`agents_api.py:193-194`), because a false comment is worse than no
comment:

```python
    # It is written into the run's state here, before loop.start, so the model never has to read
    # an id out of prose and decide to look it up. Today only the Library save reads it, to tick
    # the idea it came from. The research does NOT read it yet, so the sheet's own angle is not
    # carried in: see design/HANDOFF-STALE.md item 3.
```

**(b) The real fix**, for whoever owns `tools/run_research.py`: read `idea_id` off the run state at
the top of `run()`, look the row up with `assets._common.by_id`, and use its `angle` when the caller
gave none. The row already carries `angle`, `format` and `linkability`; `build_assets` paid for all
three.

---

## 4. `system.md` still asks the model to wait at the brand pack — `seo_agent/prompts/system.md:25`

**Most of this item was fixed while this sweep ran.** The owner of `system.md` rewrote the topic
route on 2026-09-10: "What to write next" (lines 33-56) now puts the top idea off the sheet as
state 2 and says outright *"`suggest_topics` predates the sheet and is all but dead. Call it only in
state 4"*. That matches what `registry.py` and `tools/suggest_topics.py` now enforce. Nothing more
to do there.

One line of the same class survives. The state table still says:

```
| **Brand pack: not built** | Run `learn_brand`. Then `show_artifact` the pack (view brand_pack,
path brand) and ask them to confirm the flagged rows and the one-line description. Their edits are
the truth. |
```

The brand pack stopped waiting on 2026-09-09 (`loop.py:206`, `WAITING_VIEWS = ("topic_list",
"article")`), and `registry.py`'s `show_artifact` description tells the model in so many words:
*"Never ask 'does this look right' about them and never wait for a reply you were not promised."*
So this row asks for exactly the thing the tool description forbids. `registry.py`'s `learn_brand`
description was fixed here; this row is the other half.

**Replace it with:**

```
| **Brand pack: not built** | Run `learn_brand`. Then `show_artifact` the pack (view brand_pack, path brand). It does not stop: say in one sentence that it is there to read, name what is flagged for their attention, and carry on. Their edits in the Knowledge tab are the truth whenever they make them. |
```

---

## 5. `loop.STAGE_FOR` has no row for `build_assets` — `seo_agent/loop.py:226-229`

```python
STAGE_FOR = {"index_site": "setup", "build_page_index": "setup", "learn_brand": "setup",
             "onboard": "setup", "refresh_site": "setup", "import_traffic": "setup",
             "suggest_topics": "topic", "run_research": "research",
             "build_blueprint": "blueprint", "write_article": "draft"}
```

Every other work tool that runs in a stage is here. `build_assets` is not, so a model-initiated
`build_assets` step emits with no stage and falls out of the stage grouping the run log draws
(`agGroupsHtml`: entries with no stage are "loose rows" before any group). The two hand-written
paths inside `loop.py` do pass one (`stage="setup"` at lines 268 and 374), which is why it looks
right when the engine is resumed at a gate and wrong when the model just calls it.

**Add:** `"build_assets": "setup",` to `STAGE_FOR`. `find_prompt` is deliberately absent (it belongs
to no stage); `build_assets` is not.

---

## 6. Two refusals point at a button that was deleted

The traffic-import affordance was removed from the Knowledge tab (`test_agents.js:318-327`: "the
traffic import is not a button, and nothing of its form is left behind"). The tool and the route
stayed, for the chat to offer. Two refusal messages still send the person to the deleted button:

- `seo_agent/tools/learn_brand.py:77-78` — *"Connect DataForSEO and run the site read again, or
  import a traffic file in Knowledge. I will not guess at this."*
- `seo_agent/brand/_common.py:253-254` — *"Connect DataForSEO and run the site read again, or
  import a traffic file in Knowledge. It will not guess."*

`system.md:57-59` already words it correctly ("connect DataForSEO, or hand over a traffic export
for `import_traffic`"), so these two are the stragglers.

**Replace, in both, `import a traffic file in Knowledge` with:**

> `tell me where a traffic export is and I will import it`

Note the phrase is split across two source lines in both files (`… or import a "` / `"traffic file
in Knowledge …`), so a literal search-and-replace on the whole phrase will not match. Edit the two
lines together.

---

## 7. Two docs describe a tool set that has not existed for a while

Both are documentation, so nothing breaks; both mislead the next person to read them.

- **`design/AGENT-PRINCIPLES.md:202`** — *"The seven work tools of the SEO Writer. Nothing else is a
  tool"*, over a table of seven. There are **twelve** (`registry.WORK_TOOLS`). Missing from the
  table: `refresh_site`, `import_traffic`, `onboard`, `build_assets`, `find_prompt`. The
  `suggest_topics` row (line 209, *"Proposes what to write about"*) should read *"Proposes six
  topics from one competitor. The fallback for a company with no asset sheet."*
- **`seo_agent/CONTRACTS.md:104`** — *"`onboard` (the first-run interview, six skippable questions,
  runs once)"*. It is **four** (`tools/onboard.py:61-66`); the two byline questions were deleted on
  2026-09-09 and the file says so at line 13. Change "six" to "four".

Also `seo_agent/CONTRACTS.md:109` gives `topics.json` a top-level `recommended` key:

```
- `topics.json`         {topics:[{…}], recommended}
```

Nothing writes it. `tools/suggest_topics.py:171-179` builds each row from seven named fields and
`recommended` is not one of them, and `prompts/suggest_topics.md:34-41` never asks for it. Mean-
while `static/js/17-agents.js:2882` looks for it **per topic**, not at the top level:

```js
      const rec = d.topics.find(t => t.recommended); a.picked = rec ? rec.id : null;
```

So `a.picked` is always `null` and the topic panel pre-selects nothing. Three places, three
different beliefs, and no producer. Left alone deliberately: which of six topics is "recommended"
is a design decision nobody has made, and inventing one to satisfy a dead reader would be worse
than the dead reader. Decide it once and then either write the field in `suggest_topics.py` (one
line) or delete both readers.

---

## 8. `build_assets` counts which methods ran the way the API says is wrong

`tools/build_assets.py:128-130` and `status()` at line 72 both work out which methods contributed
by counting the `method` field on the rows:

```python
    ran = sorted({m for r in rows for m in (r.get("method") or [])})
```

`agents_api.py:1949-1954` explains why that is the wrong source, and it is right:

> Counting rows cannot tell a method that RAN AND FOUND NOTHING from one that never ran at all, and
> those are different facts a person needs.

`_work/merge/methods.json` records all three states and a ready-made sentence. Not changed here
because item 1 has to settle that file's shape first: fix the shape, then move `build_assets`'
`ran`/`blocked` on to the record, and the summary line the model reads ("2 of 3 methods
contributed") stops lying about a method that ran and found nothing.

---

# What was fixed in place (the owned files)

| File | Line then | What it claimed | Now |
|---|---|---|---|
| `registry.py` | 252-268 | `suggest_topics`: *"Use when the user has not named a topic."* No mention of the sheet | Named the FALLBACK, told the model not to call it when the sheet has ideas, named the DataForSEO precondition it hard-refuses on (`tools/suggest_topics.py:118-122`) |
| `tools/suggest_topics.py` | 104-116 | ran unconditionally, straight to a paid competitor pull | Refuses when a sheet with open ideas exists, hands back the next idea and the top six open rows, spends nothing. A named competitor still overrides, because that is a person asking for this tool |
| `registry.py` | 181-190 | `onboard`: *"who articles are published under, who signs the leadership pieces… Six short questions"* | Four, and the two byline questions named as deleted. Ground truth: `tools/onboard.py:61-66` (`QUESTIONS` has four) and its own deletion note at line 13 |
| `registry.py` | 298-304 | `build_blueprint`: *"Turn the approved research… Run after the user approves the research brief"* | The research brief stopped waiting on 2026-09-09 (`loop.py:206`, `WAITING_VIEWS = ("topic_list", "article")`). Now says show it and carry straight on |
| `registry.py` | 316-324 | `write_article`: *"from the approved blueprint… Run only after the blueprint is approved"* | Same: the blueprint does not stop the run either |
| `registry.py` | 204-212 | `learn_brand`: *"show_artifact the brand pack so the user confirms the flagged rows"* | Says plainly that it does not stop, which is what `registry.py:56-61` (show_artifact) already told the model |
| `registry.py` | 227-249 | `build_assets`: named only `learn_brand` as a precondition | Names both refusals it actually has (`tools/build_assets.py:80` no site index, `:88` no brand pack), and says the sheet it leaves is where topics come from afterwards |
| `tests/test_tools.py` | new | — | Seven checks: with a sheet it refuses and names `a0001`, offers only open rows, writes no `topics.json`; a named competitor still runs; a fully-written sheet does not block it |
| `tests/test_endtoend.py` | new | — | Six checks tied to `loop.WAITING_VIEWS` rather than to a word list: no tool that follows a shown-and-passed artifact may claim it waits for an approval; `onboard`'s description must agree with `onboard.IDS`; `suggest_topics` must name the sheet |

`prompts/suggest_topics.md` was read and left alone. It is only reached now in the no-sheet case,
where every line of it is still true.

`bash seo_agent/tests/run_all.sh` → ALL SUITES PASS.
