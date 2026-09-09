# HANDOFF — layer 01 (brand), 2026-09-09

Changes layer 01 needs in files it does not own. Each one is written out exactly, with the reason,
so whoever owns the file can apply it without re-deriving anything.

Three jobs produced this list: **A** `pricing.md` (finding 8.21), **B** deleting the byline feature
(findings 8.5 + 8.22), **C** the brand-limitation reversion (finding 8.8).

---

## 1. `seo_agent/tests/test_behaviour.py` — BREAKS RIGHT NOW (job B)

The suite dies on its import line: `seo_agent/brand/voices.py` is deleted.

**Line 119**

```python
from seo_agent.brand import _common as cm, brand_facts, voices
```
becomes
```python
from seo_agent.brand import _common as cm, brand_facts
```

**Lines 137-138** — the interview is four questions now, not six.

```python
ok("all six are on record as skipped, none as an empty answer",
   len(led) == 6 and all(a["state"] == "skipped" and a["text"] == "" for a in led.values()), led)
```
becomes
```python
ok("all four are on record as skipped, none as an empty answer",
   len(led) == 4 and all(a["state"] == "skipped" and a["text"] == "" for a in led.values()), led)
```

**Lines 156-158** — delete the block entirely. There is no builder and no file any more.

```python
vout = voices.run(sh.company(), lambda a, b="": None)
ok("voices.md is kept as the team's own file, never regenerated",
   "voices.md" in (vout.get("files") or []) and "Asked at setup" in (store.knowledge("brand/voices.md") or ""))
```

**Line 162**

```python
for f in ("stats.md", "stories.md", "voices.md"):
```
becomes
```python
for f in ("stats.md", "stories.md"):
```

---

## 2. `seo_agent/tests/test_loop.py` — FOUR CHECKS FAIL RIGHT NOW (job B)

Failing: *it says which question this is* · *the answer the model finally sees…* · *the competitor
answer went to competitors.json…* · *the byline answer went to voices.md*. All four are the same
cause: the suite feeds six answers to a four-question interview.

**Line 124** — the comment.

```python
# Its own data dir. This writes real brand files (stats.md, stories.md, voices.md) and every
```
becomes
```python
# Its own data dir. This writes real brand files (stats.md, stories.md) and every
```

**Line ~152**

```python
ok("it says which question this is", s["waiting_on"]["step"] == 1 and s["waiting_on"]["of"] == 6,
```
becomes
```python
ok("it says which question this is", s["waiting_on"]["step"] == 1 and s["waiting_on"]["of"] == 4,
```

**Lines ~172-175** — two of the four answers were the byline ones. Drop them.

```python
for said in ("We shipped a video interview nobody used, and cut it.",
             "Example Team, https://example.com/author/team",
             "Ada Lovelace, CEO, https://example.com/author/ada",
             "rival-one.com and https://www.rival-two.com/pricing"):
```
becomes
```python
for said in ("We shipped a video interview nobody used, and cut it.",
             "rival-one.com and https://www.rival-two.com/pricing"):
```

**Lines ~181-184**

```python
ok("six questions, ONE tool result: the model never sees a half-finished interview",
   len(results) == 1, len(results))
ok("the answer the model finally sees says what was answered and what was passed over",
   "5 of 6 answered" in str(results[0]["content"].get("summary", "")), results[0]["content"])
```
becomes
```python
ok("four questions, ONE tool result: the model never sees a half-finished interview",
   len(results) == 1, len(results))
ok("the answer the model finally sees says what was answered and what was passed over",
   "3 of 4 answered" in str(results[0]["content"].get("summary", "")), results[0]["content"])
```

**Line 187** — delete. There is no voices.md.

```python
ok("the byline answer went to voices.md", "Ada Lovelace" in (store.knowledge("brand/voices.md") or ""))
```

---

## 3. `static/js/17-agents.js` — ALREADY DONE, one thing to reconcile (jobs A + B)

`AG_BRAND_FILES` is a hand-kept mirror of `brand/pack.FILES`, and the panel prints
"**N of AG_BRAND_FILES.length** files built" from it, so the two lists have to hold the same names
or the count goes wrong. Checked 2026-09-09: the UI owner has **already** dropped the `voices.md`
row and added a `pricing.md` one, and both lists are now 18 long. Nothing more is needed — the row
routes through the existing `data-ag="brandfile"`, which opens `/knowledge/brand/pricing.md` in the
side panel with Edit and Save, and the builder now puts a blank `pricing.md` on disk on every run,
so the row is never disabled.

**One divergence.** The same file is described twice, differently:

| Where | The line |
|---|---|
| `17-agents.js` | "What each plan costs and the things the site does not say out loud. You type this one." |
| `brand/pack.LABELS` | "Anything your site draws with JavaScript, so a crawler cannot see it. Prices, plans, trial length. Type it here and it beats anything we read off the site." |

The second is the wording the owner's note asked for, and it says the two things a person needs to
know: *why* a crawler cannot see it, and that what they type outranks the crawl. Whoever owns the
JS should take that wording, so the brand-pack panel and the Knowledge screen do not describe the
same file two ways.

---

## 4. `agents_api.py` — two additions (job A)

### 4a. Rebuild `features.md` the moment somebody saves `pricing.md`

**Without this the feature still works**: `features.pricing_stale()` compares a fingerprint of
`pricing.md` against the one `features.md` was filled from, and `learn_brand` gives the features
builder a look whenever they differ. This hook only makes it *immediate* instead of *at the next
brand-pack run*.

In `api_save_brand_file` (line ~643), after `store.save_knowledge("brand/" + name, data)`:

```python
    store.save_knowledge("brand/" + name, data)
    # PRICING.MD IS THE ONE BRAND FILE A SAVE HAS TO PROPAGATE. It carries facts the crawler can
    # never reach (JS-rendered prices), and features.md — the file the writer reads for product
    # claims — is filled FROM it. Marking it is all that happens here: the rebuild reuses the
    # cached crawl and still costs two model calls, which a save must not sit and wait for.
    # The chain is one hop by the owner's decision (2026-09-09): pricing.md -> features.md, and
    # NOT on to writing-integrity.md or writer-brief.md.
    if name == "pricing.md":
        try:
            from seo_agent.brand import features
            features.pricing_saved()
        except Exception:  # noqa: BLE001 -- the engine may not be installed; the save still stands
            pass
    return {"ok": True}
```

`features.pricing_saved()` writes only `brand/_work/features/pricing-stamp.json` and returns
whether a rebuild is now due. It makes no model call and touches no other file.

### 4b. Show the typed-in files on the Knowledge screen

`pack.inputs()` is ready and returns rows in the same shape as `built_from` / `extras`
(`{name, label, note, exists, words}`). In `_brand_knowledge()` (line ~418):

```python
        return {"brand": sh.company()["brand"],
                "brief": pack.brief(),
                "built_from": pack.built_from(),
                "inputs": pack.inputs(),          # files a PERSON fills in; pricing.md is the first
                "extras": pack.extras(),
                "cta": {"count": cta.count()}}
```

and the same key added to the `except` fallback below it (`"inputs": []`). The JS then wants a
small section next to `agExtrasHtml`, opening each row with the existing `data-ag="brandfile"`
route. Not urgent: the file already has a working door in the brand-pack panel via item 3.

---

## 5. `seo_agent/CONTRACTS.md` — the brand file list (jobs A + B)

Line 57, the "Brand files (knowledge/brand/), in build order" list. `voices.md` out, `pricing.md`
in, immediately before `features.md`, so it matches `brand/pack.FILES`:

```
type-roles.json · stats.md · stories.md · page-shortlist.md · brand-voice.md · style-guide.md ·
pricing.md · features.md · cta-pages.md · writing-examples.md · persona.md · writing-integrity.md ·
writer-brief.md · writer-brief-rulings.md · brand-cards.json · field-sources.md · seo-aeo-geo-checklist.md
```

Worth a line under it, in the same spirit as the `opinions.md` note already there:

> `voices.md` and the byline questions were removed on 2026-09-09, on the owner's word: *"remove
> completely everything about the byline questions, everything from Sutra for now."* The writer
> brief is now built from three sources, not four. `pricing.md` is the one file in this list a
> person writes and no builder does: prices and anything else a site renders with JavaScript, which
> a crawler cannot reach. Saving it rebuilds `features.md` and nothing else.

---

## 6. `seo_agent/tests/_fixture.py` — cosmetic (job B)

Line 621, the stubbed writer brief, still emits a `## Who is writing` section. The real template no
longer has one, so the stub is now describing a document the builder cannot produce. Nothing fails
on it. Remove `"## Who is writing\n%s Team, in the first person plural.\n\n"` and its `%s`.

---

## 7. `seo_agent/write/write_body.py` — FINDING 8.8, the brand-limitation reversion (job C)

**Where the finding really is.** I was asked to look for it in the brand layer. It is not there.
Verified both ways:

- His 2026-09-05 fix lives in exactly one place in his tree —
  `workflows/04-write-phase/scripts/write_body.py:283-286` — and in the two format profiles
  (`formats/listicle.md:48`, `formats/comparison-rankings.md:43`), which Sutra already carries
  byte-identical, with `test_prompts_parity.py:130-137` asserting them.
- `grep -rin limitation` over his whole `workflows/01-brand-context/` returns **nothing**.
- Sutra's brand-layer honesty contract, `prompts/brand/templates/writing-integrity.md`, is
  byte-identical to his `03-content-machine/reference/writing-integrity/writing-integrity.md` apart
  from the two documented fills (`{{BRAND}}` in the title, and the competitor list pointing at
  `knowledge/competitors.json` instead of his repo path). Its Rules 2 and 3 — "say when we're NOT
  the right fit", "acknowledge limitations" — are his own current wording and must stay.

So the brand layer is clean and the one-line reversion is in the write phase, which I do not own.

**His code**, `workflows/04-write-phase/scripts/write_body.py:283-286`:

```python
        # 2026-09-05 (Testlify review): the "name one honest limitation" clause is gone — a published
        # article must never volunteer the publisher's own weaknesses. Honest scope, no self-criticism.
        rule = (f"This section IS about {brand}. Cover it factually and fairly from the facts above, and "
                f"never oversell or invent a capability. Never volunteer a limitation, weakness or gap of "
                f"{brand}: state what it does and who it is for, then stop. Scope stated plainly is fine "
                f"(built for X); a drawback written as a drawback is not."
```

**Sutra's**, `seo_agent/write/write_body.py:203-205`:

```python
        rule = (("This section IS about %s. Cover it factually and fairly from the facts above, name at "
                 "least one honest limitation, and never oversell or invent a capability.") % brand["brand"]
                if is_brand else
```

**The change** — his wording, kept whole:

```python
        # 2026-09-05 (his Testlify review): the "name one honest limitation" clause is GONE. A
        # published article must never volunteer the publisher's own weaknesses — honest scope, no
        # self-criticism. Sutra shipped the pre-fix line while already carrying the post-fix rule in
        # formats/listicle.md and formats/comparison-rankings.md, so the two disagreed (finding 8.8).
        rule = (("This section IS about %s. Cover it factually and fairly from the facts above, and "
                 "never oversell or invent a capability. Never volunteer a limitation, weakness or gap "
                 "of %s: state what it does and who it is for, then stop. Scope stated plainly is fine "
                 "(built for X); a drawback written as a drawback is not.")
                % (brand["brand"], brand["brand"])
                if is_brand else
```

Worth a check in `test_write.py` alongside the format-profile ones in `test_prompts_parity.py`:
the brand-section rule says *never volunteer a limitation* and never *name at least one*.
