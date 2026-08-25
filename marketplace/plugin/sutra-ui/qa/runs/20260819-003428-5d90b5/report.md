# design-qa report — 20260819-003428-5d90b5

| | |
|---|---|
| Verdict | **FAIL** |
| URL | http://127.0.0.1:8330/ |
| Started | 2026-08-18T19:04:28.115Z |
| Duration | 16.1s |
| States | 8 |
| Screenshots | 7 |
| Checks | 71 |
| Failures | 12 |

## Findings (ranked, failures first)

| # | rule | state | selector | detail |
|---:|---|---|---|---|
| 1 | state-capture | log-open | `-` | state failed before rules could run: page.waitForSelector: Timeout 10000ms exceeded. Call log: [2m  - waiting for locator('#panes .gv-log .gv-ln.bad') to be visible[22m  |
| 2 | token-compliance | boot | `.pane .pb, .pane .pb *` | 1 off-token color(s): color=rgb(0,0,0) on button.trow.ok |
| 3 | token-compliance | chip-open | `.pane .pb, .pane .pb *` | 2 off-token color(s): color=rgb(0,0,0) on button.trow.ok; background-color=rgba(0,0,0,0.22) on pre.md-pre |
| 4 | token-compliance | collapsed-pane | `.pane .pb, .pane .pb *` | 1 off-token color(s): background-color=rgba(0,0,0,0.22) on pre.md-pre |
| 5 | token-compliance | dark | `.pane .pb, .pane .pb *` | 2 off-token color(s): color=rgb(0,0,0) on button.trow.ok; background-color=rgba(0,0,0,0.22) on pre.md-pre |
| 6 | token-compliance | fanout | `.pane .pb, .pane .pb *` | 1 off-token color(s): background-color=rgba(0,0,0,0.22) on pre.md-pre |
| 7 | token-compliance | light | `.pane .pb, .pane .pb *` | 2 off-token color(s): color=rgb(0,0,0) on button.trow.ok; background-color=rgba(0,0,0,0.22) on pre.md-pre |
| 8 | token-compliance | reduced-motion | `.pane .pb, .pane .pb *` | 2 off-token color(s): color=rgb(0,0,0) on button.trow.ok; background-color=rgba(0,0,0,0.22) on pre.md-pre |
| 9 | focus-visible | collapsed-pane | `.gv-chip` | button.gv-chip: no visible focus indicator |
| 10 | focus-visible | dark | `.gv-chip` | button.gv-chip: no visible focus indicator; button.gv-chip: no visible focus indicator |
| 11 | focus-visible | light | `.gv-chip` | button.gv-chip: no visible focus indicator; button.gv-chip: no visible focus indicator |
| 12 | focus-visible | reduced-motion | `.gv-chip` | button.gv-chip: no visible focus indicator; button.gv-chip: no visible focus indicator |

## Checks by rule

| rule | pass | fail |
|---|---:|---:|
| token-compliance | 0 | 7 |
| contrast | 28 | 0 |
| reduced-motion | 7 | 0 |
| overflow | 7 | 0 |
| focus-visible | 17 | 4 |
| state-capture | 0 | 1 |

## States

### boot

![boot](01-boot.png)

Screenshot: `01-boot.png`

Checks: 10 — failures: 1

- FAIL [token-compliance] `.pane .pb, .pane .pb *`: 1 off-token color(s): color=rgb(0,0,0) on button.trow.ok

### fanout

![fanout](02-fanout.png)

Screenshot: `02-fanout.png`

Checks: 10 — failures: 1

- FAIL [token-compliance] `.pane .pb, .pane .pb *`: 1 off-token color(s): background-color=rgba(0,0,0,0.22) on pre.md-pre

### log-open

Screenshot: none (state errored before capture)

Error: page.waitForSelector: Timeout 10000ms exceeded. Call log: [2m  - waiting for locator('#panes .gv-log .gv-ln.bad') to be visible[22m 

Checks: 1 — failures: 1

- FAIL [state-capture] `-`: state failed before rules could run: page.waitForSelector: Timeout 10000ms exceeded. Call log: [2m  - waiting for locator('#panes .gv-log .gv-ln.bad') to be visible[22m 

### chip-open

![chip-open](04-chip-open.png)

Screenshot: `04-chip-open.png`

Checks: 10 — failures: 1

- FAIL [token-compliance] `.pane .pb, .pane .pb *`: 2 off-token color(s): color=rgb(0,0,0) on button.trow.ok; background-color=rgba(0,0,0,0.22) on pre.md-pre

### collapsed-pane

![collapsed-pane](05-collapsed-pane.png)

Screenshot: `05-collapsed-pane.png`

Checks: 10 — failures: 2

- FAIL [token-compliance] `.pane .pb, .pane .pb *`: 1 off-token color(s): background-color=rgba(0,0,0,0.22) on pre.md-pre
- FAIL [focus-visible] `.gv-chip`: button.gv-chip: no visible focus indicator

### dark

![dark](06-dark.png)

Screenshot: `06-dark.png`

Checks: 10 — failures: 2

- FAIL [token-compliance] `.pane .pb, .pane .pb *`: 2 off-token color(s): color=rgb(0,0,0) on button.trow.ok; background-color=rgba(0,0,0,0.22) on pre.md-pre
- FAIL [focus-visible] `.gv-chip`: button.gv-chip: no visible focus indicator; button.gv-chip: no visible focus indicator

### light

![light](07-light.png)

Screenshot: `07-light.png`

Checks: 10 — failures: 2

- FAIL [token-compliance] `.pane .pb, .pane .pb *`: 2 off-token color(s): color=rgb(0,0,0) on button.trow.ok; background-color=rgba(0,0,0,0.22) on pre.md-pre
- FAIL [focus-visible] `.gv-chip`: button.gv-chip: no visible focus indicator; button.gv-chip: no visible focus indicator

### reduced-motion

![reduced-motion](08-reduced-motion.png)

Screenshot: `08-reduced-motion.png`

Checks: 10 — failures: 2

- FAIL [token-compliance] `.pane .pb, .pane .pb *`: 2 off-token color(s): color=rgb(0,0,0) on button.trow.ok; background-color=rgba(0,0,0,0.22) on pre.md-pre
- FAIL [focus-visible] `.gv-chip`: button.gv-chip: no visible focus indicator; button.gv-chip: no visible focus indicator

