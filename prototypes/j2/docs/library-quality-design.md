# Library quality: design (Phase 0)

For Sankalp, Rubak and Kaivan. Written 2026-11-17 on branch `library-quality`. Design only: no code is changed.

**What this is.** Every template is still saved to the library. Quality decides four things only: the template's
tier, its rank in search, whether it is shown, and whether the router may pick it for another business without being
asked. All of it is behind `J2_LIBRARY_QUALITY=1`; with the flag off the library behaves as it does today.

**Three findings from today's data that change the design** (details in sections 3 and 9):

| # | Finding | Effect |
|---|---|---|
| 1 | No template reaches Quality 0.70 today. The best is Calm Core Pilates v1 at 0.64. | With the flag on, nothing is Proven, so no template is picked across businesses. |
| 2 | A template used only by its own business cannot reach 0.70 in practice (generality is 0, so it needs about 9 clean uses and an efficiency baseline). Candidates are own-business only, so they never get the other-business use that would lift them. | A cold-start rule is needed. Recommended: score evidence per family (section 5), which makes the 20-workflow family Proven at 0.74. |
| 3 | `used_by` misses runs that crashed or never finished. Still Point Yoga's template lists 2 uses; the run folders show 4. | Outcome is counted from the runs' own `templates.json`, not from `used_by` alone. |

## 0. Scope and files

| Item | Where | Owner |
|---|---|---|
| Signals, score, tiers, families, router gate | `j2_template_lib.py` | ours |
| Weights, thresholds, penalties | `templates/library-settings.json`, new `quality` block | ours |
| Scores, tier log, human signal, families | `library/quality/` (new folder) | ours |
| Library tab | `j2_ui.html`, Library parts only | ours |
| One POST route for thumbs, feature and approve | `j2_server.py` | not ours: own commit, "j2_server.py (needs owner review)" |
| Any change to `j2.py` | `j2.py` | not ours: own commit, "j2.py (needs owner review)". None is needed for Phases 1 to 4. |

Two kinds of template are scored the same way: a **run template** (a whole run's workflows) and a **section
template** (one section's fields). The worked example is on run templates, because those are what a run picks first.

## 1. Signals

Every signal is computed from files a run already records. Nothing new is recorded by `j2.py`.

**A use** is one run that started from the template. The run the template was made from is not a use.

| Signal | What it measures | Exact source | Value |
|---|---|---|---|
| Outcome | Share of uses that ended workable | Uses: every run whose `templates.json` has `run_template.id` equal to this template, plus the runs in the template's `used_by`. Workable: `summary.json` has `"workable": []` and `status` is not `crashed`. | Wilson lower bound of workable / known uses |
| First try | Share of section fills that passed schema and rules on attempt 1 | `receipts.jsonl` rows with `type` `artifact-schema` or `artifact-rules` and `attempt` 1, grouped by `atom`; a fill passes when all its rows have `pass: true`. Counted over the maker run and every use. | Wilson lower bound of passed / fills |
| Rework | Share of workflows that were fixes or failed, and audit failures | `workflows.json`: a workflow with `revises` set is a fix; `status: failed` is a failure. `audits.json`: results with `verdict: NEEDS_REVISION`. | Shown, and used by the tier rules. Not in the score (see decision D4). |
| Generality | Distinct businesses that used it | `goal.json` `site_name` (else `product_name`) of each use, plus the maker's business | (businesses - 1) / 2, at most 1. Own business only is 0; three businesses is 1. |
| Efficiency | AI calls and tokens against fresh builds | `timing.json` `ai.calls`, `ai.tokens_in`, `ai.tokens_out`, each divided by the run's finished workflows (`workflows.json` `status: done`). Baseline: median of live finished runs with the same stages and no run template. | 0.5 + (1 - ratio), kept between 0 and 1, where ratio is the mean of the calls ratio and the tokens ratio. No baseline or no use: 0.5. |
| Structure health | Six checks on the template itself | `spec.json` of each section template it names; `template.json` of the run template | Mean of the six checks below |
| Human signal | Thumbs up or down, feature, approve, retire | `library/quality/feedback.jsonl` (new) | Not in the score. Approve is what makes a Proven template Curated. |

Structure health, each check from 0 to 1:

| Check | Rule | Source |
|---|---|---|
| Keeps generic fields | `keeps_problems(generic, template)` is empty | `spec.json`, the artifact's `generic.json` |
| Has descriptions | Share of fields (objects' fields included) with a description | `spec.json` `fields`, `objects` |
| Has rules | 1 when `rules` is not empty | `spec.json` `rules` |
| No leaked facts | 1 minus the share of fields and `covers` lines that hold the maker's business name, an email, a phone number, a clock time or a number of 3 or more digits | `spec.json` descriptions and enums; `template.json` workflow names and `covers` |
| Not over-strict | 1 minus the share of fields that allow only listed exact values (`enum` set) | `spec.json` |
| Not empty | 1 when it has at least one field (run template: at least one workflow with a `covers` line) | `spec.json`, `template.json` |

Uses that cannot be judged are listed, not counted: a run whose folder is not saved, and a run with no `summary.json`
(stopped before it ended). A crashed run counts as not workable.

## 2. Score

Rates use the Wilson lower bound, so 2 of 2 does not score like 20 of 20:

```
lower = (p + z²/2n - z·sqrt(p(1-p)/n + z²/4n²)) / (1 + z²/n)      p = successes / n; 0 when n = 0
```

| Successes / n | z = 1.0 | z = 1.96 |
|---|---|---|
| 1 / 1 | 0.50 | 0.21 |
| 2 / 2 | 0.67 | 0.34 |
| 3 / 3 | 0.75 | 0.44 |
| 5 / 5 | 0.83 | 0.57 |
| 18 / 20 | 0.81 | 0.70 |
| 1 / 10 | 0.04 | 0.02 |

```
Quality = 0.35 outcome + 0.20 first try + 0.15 generality + 0.15 structure + 0.15 efficiency - penalties      (never below 0)
```

| Penalty | Amount | When |
|---|---|---|
| Leaked facts | 0.15 x leak share | always |
| Over-strict | up to 0.10, rising from 0 at 40% exact-value fields to 0.10 at 100% | above 40% |
| Mock-made | 0.30 | the maker run was a mock run |

I recommend z = 1.0, not 1.96. With 1.96 a template used cleanly by two businesses needs about 16 clean uses to reach
0.70; with 1.0 it needs 4 (decision D1).

All numbers live in `templates/library-settings.json`; code reads them and repeats none:

```json
"quality": {
  "wilson_z": 1.0,
  "weights": {"outcome": 0.35, "first_try": 0.20, "generality": 0.15, "structure": 0.15, "efficiency": 0.15},
  "generality_full_businesses": 3,
  "efficiency_neutral": 0.5,
  "penalties": {"leaked_facts_max": 0.15, "over_strict_above": 0.40, "over_strict_max": 0.10, "mock_made": 0.30},
  "tiers": {"proven_min_uses": 2, "proven_min_quality": 0.70, "proven_demote_below": 0.65,
            "retired_below": 0.50, "retired_window_uses": 5, "retired_min_uses": 2}
}
```

## 3. Worked example: today's run templates

Read from the loop library (`/tmp/j2-loop-lib`), the id-fix library (`/tmp/j2-fix-lib`) and the saved runs in the
three run folders, all read only. z = 1.0. Computed with a throwaway script, not committed; Phase 1 writes the same
arithmetic into `j2_template_lib.py` and its test checks these numbers.

Evidence:

| Template | Made from | Uses that ended workable | Not counted | First try | Rework in uses | Businesses |
|---|---|---|---|---|---|---|
| Calm Core Pilates v1 | j2-20261117-145217 | 2 of 2 (Zen Barre, Calm Core Pilates) | none | 62 of 67 | 7 of 47 workflows | 2 |
| Still Point Yoga: PRD, HLD and LLD | j2-20261103-184249 | 2 of 3 (Iron Grove crashed once, then finished; Rhythm Room finished) | 1 unfinished | 69 of 88 | 23 of 63 workflows | 3 |
| Iron Grove Fitness | j2-20261111-211339 | 1 of 1 (Calm Core Pilates) | 1 not saved (Flow Pilates), 1 unfinished | 45 of 53 | 1 of 21 workflows | 2 |
| Calm Core Pilates v2 | j2-20261117-153301 | 0 of 0 | none | 22 of 22 | none | 1 |
| Zen Barre Studio | j2-20261117-151050 | 0 of 0 | none | 20 of 24 | none | 1 |
| Clear Counsel | j2-20261117-164922 | 0 of 0 | none | 4 of 6 | none | 1 |
| Still Point Yoga: studio website (mock) | j2-20261103-161111-3 | 0 of 0 | none | 24 of 24 | none | 1 |
| Thread boutique website (mock) | j2-20261103-161111 | 0 of 0 | maker run not saved | 0 of 0 | none | 1 |

Signals and score:

| Template | Outcome | First try | Generality | Structure | Efficiency | Leak share | Exact-value share | Penalties | **Quality** | Tier |
|---|---|---|---|---|---|---|---|---|---|---|
| Calm Core Pilates v1 | 0.67 | 0.89 | 0.50 | 0.90 | 0.50 | 39% | 20% | 0.06 | **0.64** | Candidate |
| Still Point Yoga: PRD, HLD and LLD | 0.39 | 0.74 | 1.00 | 0.90 | 0.50 | 28% | 29% | 0.04 | **0.60** | Candidate |
| Iron Grove Fitness | 0.50 | 0.79 | 0.50 | 0.91 | 0.50 | 34% | 20% | 0.05 | **0.57** | Candidate |
| Calm Core Pilates v2 | 0.00 | 0.96 | 0.00 | 0.90 | 0.50 | 43% | 19% | 0.06 | **0.34** | Candidate |
| Zen Barre Studio | 0.00 | 0.74 | 0.00 | 0.90 | 0.50 | 40% | 20% | 0.06 | **0.30** | Candidate |
| Clear Counsel | 0.00 | 0.46 | 0.00 | 0.92 | 0.50 | 6% | 30% | 0.01 | **0.30** | Candidate |
| Still Point Yoga: studio website (mock) | 0.00 | 0.96 | 0.00 | 0.87 | 0.50 | 46% | 20% | 0.37 | **0.03** | Candidate, never promoted |
| Thread boutique website (mock) | 0.00 | 0.00 | 0.00 | 0.85 | 0.50 | 76% | 14% | 0.41 | **0.00** | Candidate, never promoted |

Calm Core Pilates v1, step by step: 0.35 x 0.667 + 0.20 x 0.887 + 0.15 x 0.50 + 0.15 x 0.902 + 0.15 x 0.50 =
0.696; minus 0.15 x 0.386 = 0.058; Quality 0.638.

What the table shows:

| Observation | Number |
|---|---|
| Calm Core v1 meets the Proven use rule (2 workable uses, 1 by another business) but not the 0.70 bar | 0.64 |
| One more clean use by a third business would take it over | about 0.74 |
| Efficiency is 0.50 for every template: no fresh four-stage build with timing is recorded | 0 baselines |
| Against the Iron Grove maker run as a stand-in baseline, Calm Core v1's uses took 0.70 of the calls and 0.66 of the tokens per workflow | Quality would be 0.69 |
| Leak share is 28% to 46% on the live templates: section templates hold their business's facts in field descriptions by design | costs 0.04 to 0.07 |
| With z = 1.96 the top score is 0.52 | Calm Core v1 |

The 12 batch runs finishing later today will be added to both tables. They should give more uses and may give the
first fresh baselines.

Section templates, scored the same way (160 versions across the two libraries; 115 have a known use, 26 are
mock-made):

| Section template | Uses that finished | First try | Outcome | Reading |
|---|---|---|---|---|
| Calm Core Pilates PRD Out of scope@1 | 3 of 3 | 3 of 3 | 0.75 | best today |
| Calm Core Pilates Data flow@1 (and 4 more HLD ones) | 2 of 2 | 2 of 2 | 0.67 | |
| Clear Counsel PRD Success metrics@1 | 1 of 10 | 1 of 10 | 0.04 | Retired. In run j2-20261117-154941 every fill was refused with "success_metrics.0.id: Extra inputs are not permitted". |

## 4. Tiers

| Tier | Rule (all parts must hold) | Shown | Auto-pick |
|---|---|---|---|
| Candidate | Every template starts here. Stays here while it has under 2 workable uses or misses a Proven rule. | To its own business, and on the Candidates shelf | Own business only |
| Proven | Live-made. At least 2 workable uses. At least 1 of them by another business, or 2 by the same business. Quality at least 0.70. | Everyone | Any business |
| Curated | Proven, and a person approved this exact version (its `sha`) | Everyone, featured first | Any business, ranked first on ties |
| Retired | Has at least 2 known uses and Quality over its last 5 uses is under 0.50; or superseded; or a person retired it | Hidden (a "Show retired" switch reveals it) | Never |

| Change | When | Automatic |
|---|---|---|
| Candidate to Proven | The Proven rule holds after a run ends | yes |
| Proven to Curated | A person approves | no |
| Proven or Curated to Candidate | Quality falls under 0.65, or the use rule no longer holds. The gap between 0.70 and 0.65 stops a template flipping on one run. | yes |
| Curated to Proven | The approved version changes (new `sha`); the approval is for one version | yes |
| Any to Retired | The Retired rule holds | yes |
| Retired to Candidate | A person restores it. A retired template is never picked, so it cannot recover by itself. | no |

Superseded means: a later version of the same family is at the same or a higher tier and its Quality is at least
this one's. A newer version with no uses does not supersede an older one. Today Calm Core v2 (0.34) does not
supersede v1 (0.64).

Mock-made templates stay Candidate whatever their score.

Tiers are recomputed when a run ends (inside `auto_save_run_template`, which `j2.py` already calls) and when the
Library page is read. Every change is appended to `library/quality/events.jsonl` with its reason:

```json
{"t": "2026-11-17T18:02:11", "template": "rt/calm-core-pilates-...-website", "from": "candidate", "to": "proven",
 "quality": 0.74, "reason": "3 workable uses of 3, 2 by other businesses (Zen Barre, Iron Grove Fitness); Quality 0.74 is at least 0.70",
 "run": "j2-20261117-190000", "by": "code"}
```

Files in `library/quality/`:

| File | Holds | Rebuildable |
|---|---|---|
| `scores.json` | Each template's signals, score, tier and the counts behind them | yes, from runs and the library |
| `events.jsonl` | Every tier change with its reason | no, append only |
| `feedback.jsonl` | Thumbs, feature, approve, retire, restore: who, when, which version | no, append only |
| `families.json` | Each family's fingerprint, members and canonical version | yes |

## 5. De-duplication

**Structural fingerprint.** A hash of the template with every fact removed.

| Kind | In the fingerprint | Left out |
|---|---|---|
| Section template | Artifact, section; each field's name, type, required, and whether it has listed values; the same for objects; each rule's kind, path and target | Template name, descriptions, the listed values, `facts_used`, who made it |
| Run template | Stages; each planned workflow's stage, artifact and section | Name, business type, `covers` text, slots, fix workflows |

Templates with the same fingerprint are one **family**. The family's canonical version is the member with the highest
Quality (ties: the higher tier, then the newer). The others are shown as its versions, not as separate cards. Nothing
is deleted or moved on disk.

Today:

| Kind | Before | Families | Largest |
|---|---|---|---|
| Section templates | 160 versions | 48 (27 of them have 1 member) | Website section: 10 versions. HLD Components and HLD Hosting: 9 each. HLD Data flow: 8 versions from 6 businesses in 1 family. |
| Run templates | 8 | 6 | Iron Grove, Calm Core v1 and Zen Barre are one family: the same 20 planned workflows |

Calm Core v2 falls outside that family only because its W-4 has "not recorded" as section and template. That is a
recording gap in `run_template_from_run`, to be fixed in Phase 2; with it fixed there are 5 families.

**Evidence per family (recommended, decision D2).** A family's uses, fills and businesses are pooled, and the tier
is decided on the pooled numbers. This is the answer to finding 2: a structure that worked for three businesses has
shown it is general, even when each business has its own wording of it.

| 20-workflow family (Iron Grove, Calm Core v1, Zen Barre) | Value |
|---|---|
| Uses that ended workable | 3 of 3, outcome 0.75 |
| First try | 87 of 99, 0.84 |
| Businesses | 3, generality 1.00 |
| Structure, efficiency, penalties | 0.90, 0.50, 0.055 |
| **Quality** | **0.74: Proven**, canonical version Calm Core Pilates v1 |

## 6. Router

With the flag on, two existing functions in `j2_template_lib.py` change; nothing else does.

| Step | Run templates (`match_run_templates`) | Section templates (`route`, `nearest_ranked`) |
|---|---|---|
| 1. Eligible by fit | Match at least 0.6, as today (0.4 stages + 0.3 business + 0.3 covers) | Coverage and business similarity limits, as today |
| 2. Eligible by tier | Same business: Candidate, Proven or Curated. Another business: Proven or Curated only. Retired and mock-made: never. | the same |
| 3. Rank | match x Quality | similarity x Quality |
| 4. Ties | Curated first, then the canonical version of a family, then the newer | the same |
| 5. Record | The decision in `templates.json` gains `quality`, `tier` and `rank`, and a `not_eligible` list with the reason for each template passed over | the same |

A person can still choose any template that is not Retired with "Use this template", including a Candidate of
another business. That use counts as evidence like any other.

With today's per-template scores, turning the flag on would have stopped this afternoon's Zen Barre run from picking
Calm Core v1 by itself. With family evidence it is picked.

## 7. Library tab

Sutra's layout and tokens are kept: the Library page's `--s-*` colours, `--display`, `--body` and `--mono` fonts,
the two shelves (`shelf/1`) and the three tabs every template already has. No new colour is added: tier badges use
`--s-good` (Proven), `--s-accent` (Curated), `--s-muted` (Candidate) and `--s-bad` (Retired).

| Part | What it shows | Data |
|---|---|---|
| Search home | One box, "What do you want to make?", above the shelves. Results are ranked as the router ranks them, for the business typed or picked. | `find_template` with Quality |
| Health strip | One line under the search box: templates per tier, families, changes in the last 7 days, templates with a thumbs-down | `scores.json`, `events.jsonl` |
| Card | Quality ring (the score as an arc, the number inside), tier badge, name, usage line ("used by 3 businesses, 3 of 3 finished cleanly"), reuse sparkline (uses per week), business chips, a "mock" mark where it applies | `scores.json` |
| Shelves | Curated, Proven, Candidates, in that order; Retired behind a switch. Within a shelf, families, canonical version on the card, "+2 versions" under it. | `families.json` |
| Detail | The three existing tabs, then four blocks below | |
| Why this score | One bar per signal with its weight, value and the counts behind it ("Outcome 0.67: 2 of 2 uses ended workable"), penalties as bars to the left, the sum, and the rule that set the tier | `scores.json` |
| Outputs gallery | The finished artifacts made from it, newest first, each linking to the Artifacts shelf | `find_artifact` |
| Version timeline | The family's versions by date, tier changes marked with their reason; picking two shows the field diff (added, removed, changed type, changed rule) | `families.json`, `events.jsonl`, `spec.json` |
| Use this template | Button; starts a run from it. For a Candidate of another business it says so first. | existing run-template start |
| Compare view | Two or three templates side by side: signals, tier, fields diff | `scores.json`, `spec.json` |
| Human signal | Thumbs up, thumbs down, Feature, Approve, Retire, Restore on the detail | `feedback.jsonl`, the one new route |

An empty count is written as "no uses yet", never as 0%. With the flag off none of these parts is drawn.

## 8. Tests and phases

`library_quality_test.py`, on fixture runs copied from today's (no live runs, no AI calls):

| Test | Checks |
|---|---|
| Wilson | The six rows of the table in section 2, at both z values; n = 0 gives 0 |
| Signals | Each signal for the 8 run templates equals the worked example |
| Uses | A crashed run counts as not workable; an unsaved or unfinished run is listed and not counted; a use missing from `used_by` is still found |
| Structure | A template with a leaked email, one with every field exact-value, an empty one: each scores as specified |
| Settings | Changing a weight in the settings file changes the score; no weight or threshold is written in code |
| Tiers | Each change in the section 4 table happens on the right input and writes one event with a reason; 0.66 does not demote, 0.64 does |
| Mock | A mock-made template is never promoted |
| Families | Two templates that differ only in facts share a fingerprint; a changed field type splits them; 160 versions give 48 families |
| Router | Flag on: a Candidate of another business is never picked, a Proven one is, rank is fit x Quality. Flag off: decisions are byte-for-byte what they are today. |
| Page | Browser check of cards, shelves, "Why this score", compare, and that nothing is drawn with the flag off |

| Phase | Work | Estimate | Changes behaviour |
|---|---|---|---|
| 1 | Signals, score, settings block, `scores.json`, tests | 1 day | no |
| 2 | Families, tiers, `events.jsonl`, the W-4 recording gap, tests | 1 day | no |
| 3 | Router gate behind the flag, tests | 0.5 day | only with the flag on |
| 4 | Library tab | 2 days | only with the flag on |
| 5 | Human signal and its route (`j2_server.py`, own commit for owner review) | 0.5 day | only with the flag on |
| 6 | Add the batch runs to the worked example, settle the decisions below, tune thresholds | 0.5 day | no |

Total about 5.5 days. Phases 1 and 2 can start before the decisions are settled.

## 9. Decisions needed

| # | Question | Recommendation | Why |
|---|---|---|---|
| D1 | Wilson z | 1.0 | 1.96 needs about 16 clean uses for Proven; 1.0 needs 4 |
| D2 | Cold start: how does a template become Proven when Candidates are own-business only? | Pool evidence per family | The 20-workflow family is Proven at 0.74 on real evidence from 3 businesses. Without it nothing is Proven today and little can become so. |
| D3 | Efficiency with no fresh build to compare against | Neutral 0.5, as scored above | The stand-in baseline (a template's maker run) flatters every template; it would move Calm Core v1 from 0.64 to 0.69 |
| D4 | Should rework be in the score? | Not yet | The given formula has no term for it. It varies a lot (5% to 37%), so it is worth a weight once the batch runs show whether it predicts outcome. |
| D5 | Runs stopped before they ended | Not counted | A person may stop a run for reasons that have nothing to do with the template. Counting them as failures would put Iron Grove at 1 of 2. |
| D6 | The 0.65 demotion line | Keep | Not in the brief; added so one run does not flip a tier |
