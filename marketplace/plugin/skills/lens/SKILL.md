---
name: lens
preamble-tier: 2
version: 1.0.0
description: |
  The inner-engine axis engine for the Flow — the generic value<->axis machine (ADR-027). For the current step, MINT the axes that matter (interrogative x mechanism), PICK only the axes that pass the decision test, and apply the resulting cross in whichever direction the step needs: DOWN (decompose), UP (generalize), or ACROSS (reframe). Use this on EVERY step of the Flow spine, after the step's type is resolved and before the Work-Atom runs — it shapes how the step is cut, never whether the step runs. Skip only when the step is a pure terminal atom whose axes are already fixed by an upstream lens call; never skip to avoid thinking about how to cut a problem.
allowed-tools: ["Bash"]
---

# LENS — the value<->axis inner engine

This is the inner engine of the Flow. A workflow type constrains the OUTER
steps of the spine; LENS shapes the INNER cut of EVERY step, always. A
resolved workflow type never switches this engine off — it only tells you
which steps to run. How each step is decomposed, generalized, or reframed is
always decided here.

There is exactly ONE hard-coded primitive in this engine: **value <-> axis**.
Everything else — Realization, Reflection, viewpoint, certainty, depth,
audience, risk — is DATA on minted instances, not schema. Nothing below is a
fixed list. You generate the axes that matter for the step in front of you.

## 0. The one primitive (the only hard-coded thing)

```
+--- THE PRIMITIVE ----------------------------------------------+
|                                                                |
|   value  <->  axis                                             |
|                                                                |
|   A VALUE is a member of an axis.                              |
|   An AXIS is a set of values.                                  |
|   Same object, seen relative to a level:                       |
|     - "high" is a VALUE on the axis "risk"                     |
|     - "risk" is itself a VALUE on the axis "factors-that-matter"|
|   So a value at one level IS an axis at the level below.       |
|                                                                |
+----------------------------------------------------------------+
```

This recursion (a value can itself be an axis) is the whole engine. You do not
need any other primitive. You do not enumerate axes ahead of time; you MINT
them for the step.

## 1. Procedure (run this on the current step)

```
Step 1  STATE the primitive ............ value<->axis (above)
Step 2  MINT axes ...................... interrogative x mechanism
Step 3  PICK axes ...................... keep only what passes the test
Step 4  CROSS .......................... product of the picked axes
Step 5  APPLY .......................... DOWN | UP | ACROSS for this step
Step 6  RECORD ......................... write LENS=... to .claude/flow-inner
```

### Step 1 — STATE the primitive

Re-anchor on value<->axis. Do not reach for a remembered list of dimensions.
The right axes for THIS step are not known until you mint them.

### Step 2 — MINT the axes that matter (interrogative x mechanism)

Generate candidate axes; do NOT pick from a fixed menu. Two generators cross
to produce candidates:

```
+--- MINTING GRID (generate, do not look up) --------------------+
|                                                                |
|   INTERROGATIVE   x   MECHANISM         ->  candidate axis     |
|   ------------        ---------             --------------     |
|   who                 audience / reader     who-reads-this     |
|   what                thing being built     output-form        |
|   why                 purpose / value       why-it-matters     |
|   how                 method / build-path    build-method      |
|   when                timing / sequence      ordering          |
|   where               surface / locus        deploy-locus      |
|   how-sure            evidence / certainty    certainty         |
|   how-much            magnitude / cost        scale             |
|   ... (mint more interrogatives and mechanisms as the step demands) ...
|                                                                |
+----------------------------------------------------------------+
```

The grid above is an EXAMPLE of the generator, not the catalogue. For a pricing
step you might mint `willingness-to-pay`; for a refactor step you might mint
`blast-radius`; for a research step you might mint `source-trust`. Each minted
axis is an instance whose NAME is data — invented for this step, discarded
after. Mint freely; the next step throws filtering it back down.

### Step 3 — PICK axes (the decision test)

A minted axis survives only if it passes the decision test. Apply it to every
candidate:

```
+--- DECISION TEST -----------------------------------------------+
|                                                                 |
|   Keep an axis IFF it changes:                                  |
|     (a) WHAT you build      (different value -> different output)|
|     OR                                                          |
|     (b) WHO reads it        (different value -> different reader)|
|                                                                 |
|   If neither changes across the axis's values -> DROP it.       |
|   Decorative dimensions cost tokens and hide the real cut.      |
|                                                                 |
+-----------------------------------------------------------------+
```

Most minted candidates die here. That is correct. A good step usually keeps 1-3
axes. Keeping more is a smell that you minted distinctions that do not move the
work.

### Step 4 — CROSS (the product of the picked axes)

The "cross" is a runtime PRODUCT over the axes you kept — it is COMPUTED, never
a stored matrix and never a fixed two-dimensional grid. With kept axes
`A = {a1,a2}` and `B = {b1,b2,b3}`, the cross is the cells of `A x B`:

```
+--- CROSS = product(picked axes) -------------------------------+
|                                                                |
|              b1        b2        b3                            |
|        +---------+---------+---------+                         |
|    a1  | a1,b1   | a1,b2   | a1,b3   |   <- each cell is one    |
|        +---------+---------+---------+      concrete sub-case   |
|    a2  | a2,b1   | a2,b2   | a2,b3   |      to build or read    |
|        +---------+---------+---------+                         |
|                                                                |
|   With 1 axis the cross is just its values (a list).          |
|   With 3+ axes it is an N-cube; you still only build the cells |
|   that survive the decision test — you do not enumerate all.   |
|                                                                |
+----------------------------------------------------------------+
```

The number of axes sets the dimensionality. The cross has no built-in shape
(not "2x2", not "quadrants") — its shape is whatever the picked axes produce
this time.

### Step 5 — APPLY (one primitive, three directions)

The same value<->axis primitive runs in whichever direction the step needs.
The direction NAMES below (Realization / Reflection / the lens family) are the
common labels people attach — they are data describing how the primitive was
pointed, not three separate machines.

```
+--- THREE DIRECTIONS OF THE ONE PRIMITIVE ----------------------+
|                                                                |
|  DOWN  decompose   value -> its axis of sub-values             |
|        (people call this "Realization")                        |
|        STOP: ATOMICITY — a value that is smallest-buildable,   |
|        i.e. an atom (Flow MODE 1). Do not split an atom.       |
|                                                                |
|  UP    generalize  axis -> a value on a higher axis            |
|        (people call this "Reflection")                         |
|        STOP: REFLEXIVITY — the rung that describes itself; the |
|        generalization that would only re-state the generaliser.|
|                                                                |
|  ACROSS reframe    swap which axis you read the value on       |
|        (people call this "the lens family" / viewpoint /       |
|         certainty / audience reframes)                         |
|        STOP: DECISION-TEST — stop reframing once another frame |
|        no longer changes what-you-build or who-reads.          |
|                                                                |
+----------------------------------------------------------------+
```

Pick the direction the step actually needs:
- The step is too big to one-shot and you know the how -> go DOWN; the
  sub-values become the step_graph (Flow MODE 2). Each sub-value recurses.
- The step is an instance of a pattern worth lifting -> go UP until reflexivity.
- The step is well-sized but framed wrong for its reader -> go ACROSS until the
  decision test stops paying.

A single step may apply more than one direction; record all axes used.

### Step 6 — RECORD

Write the chosen axes to the inner marker so the Flow gate can see the inner
engine ran for this step:

```bash
mkdir -p "${CLAUDE_PROJECT_DIR:-.}/.claude"
printf 'LENS=%s CYNEFIN=%s FACTORS=%s TS=%s\n' \
  "<comma-separated-picked-axes>" \
  "<cynefin-domain-or-unset>" \
  "<count-of-picked-axes>" \
  "$(date +%s)" \
  > "${CLAUDE_PROJECT_DIR:-.}/.claude/flow-inner"
```

`LENS` is the comma-separated list of the axes you PICKED (not the ones you
minted-and-dropped). `CYNEFIN` carries the step's Cynefin domain if a cynefin
pass set it, else leave a placeholder such as `unset`. `FACTORS` is the count
of picked axes (the cross's dimensionality). Example value:

```
LENS=who-reads-this,output-form,certainty CYNEFIN=complicated FACTORS=3 TS=1718323200
```

## 2. Default seeds (offered every time; everything else minted)

Two seeds are offered on EVERY step so you never start from a blank grid. They
are still INSTANCES of the primitive — defaults, not schema. You may drop
either if it fails the decision test for the step.

```
+--- DEFAULT SEEDS ----------------------------------------------+
|                                                                |
|   SEED 1  Realization  (DOWN)  — can this value be cut into    |
|           smaller buildable values? Stop at atomicity.         |
|                                                                |
|   SEED 2  Reflection   (UP)    — is this value an instance of  |
|           a higher pattern worth lifting? Stop at reflexivity. |
|                                                                |
|   Everything else (viewpoint, certainty, audience, scale,      |
|   timing, risk, ...) is MINTED ON DEMAND via Step 2 and kept   |
|   only via Step 3. None of those names is privileged.          |
|                                                                |
+----------------------------------------------------------------+
```

## 3. Generic data model (the engine in shape form)

This is the entire type surface. Implement-in-your-head as you walk a step.

```
Axis  = { name: data, values: Value[] }        # an axis is a set of values
Value = Scalar | Axis                          # a value may itself be an axis
                                               # (this is the recursion)

mint(step)            -> Axis[]   # interrogative x mechanism; GENERATE, no list
pick(Axis[], step)    -> Axis[]   # keep iff changes what-built OR who-reads
product(Axis[])       -> Cell[]   # the cross; COMPUTED, never stored/fixed
                                  # Cell = one tuple of values, one sub-case

# three stops bound the three directions:
stop_down  = atomicity     # Value is smallest-buildable -> it is an atom
stop_up    = reflexivity   # the rung that describes itself
stop_across= decision-test # reframing no longer changes built/reader
```

Notes that matter:
- `name` on both Axis and Value is **data**. "Realization", "Reflection",
  "viewpoint", "certainty" are names that land on minted instances. They are
  not enumerated members of the engine.
- `product()` is a runtime computation. There is no canonical cross, no fixed
  2x2, no privileged pair of axes. The cross's shape = the axes you picked
  this time.
- `Value = Scalar | Axis` is what makes DOWN, UP, and ACROSS the same machine:
  going DOWN reads a Value as an Axis; going UP reads an Axis as a Value on a
  higher Axis; going ACROSS swaps which Axis a Value is read against.

## 4. What is hard-coded vs. what is data (read twice)

```
+--- THE BOUNDARY -----------------------------------------------+
|                                                                |
|   HARD-CODED (the only thing):                                |
|     value <-> axis   (a value is a member of an axis;          |
|                       an axis is a set of values)              |
|                                                                |
|   DATA (minted, picked, discarded per step):                  |
|     - every axis NAME (who-reads / output-form / certainty...) |
|     - the cross (a runtime product, recomputed each step)      |
|     - the direction labels (Realization / Reflection /         |
|       viewpoint / certainty / the lens family)                 |
|     - the number and shape of dimensions                       |
|                                                                |
|   Do NOT hard-code axis names. Do NOT hard-code a fixed cross. |
|   Do NOT treat Realization/Reflection as schema. Mint, pick,   |
|   product, stop.                                               |
|                                                                |
+----------------------------------------------------------------+
```

## 5. Worked micro-example (illustrative — not a template)

Step: "write the pricing section of a product page."

1. STATE: value = "pricing section"; it is a value on some axis to be minted.
2. MINT (interrogative x mechanism): `who-reads-this` (who x audience),
   `tier-structure` (what x packaging), `willingness-to-pay` (how-much x
   value), `font-choice` (what x styling).
3. PICK (decision test): keep `who-reads-this` (founder vs buyer changes copy),
   keep `tier-structure` (changes what is built). DROP `willingness-to-pay`
   (informs but does not by itself change THIS section's build), DROP
   `font-choice` (decorative — fails both clauses).
4. CROSS: product(who-reads-this {founder, buyer} x tier-structure
   {free, pro, enterprise}) = 6 cells; build only the cells that survive
   (buyer x {free,pro,enterprise} are the live ones to write).
5. APPLY: direction = DOWN (decompose into the surviving cells, each a buildable
   atom-sized sub-part). No UP (no higher pattern worth lifting here). No ACROSS
   beyond the audience reframe already captured by `who-reads-this`.
6. RECORD: `LENS=who-reads-this,tier-structure CYNEFIN=complicated FACTORS=2`.

The axis names above were invented for this step and are gone after it. The
next step mints its own.

## 6. Composes with the rest of the Flow

- Runs on EVERY step, after type-resolution, before the Work-Atom executes.
- Feeds the step_graph when you go DOWN (sub-values become sub-steps; each
  recurses through the same spine).
- The `CYNEFIN` field is carried so a cynefin pass and this lens pass write the
  same `.claude/flow-inner` marker coherently.
- Halting: DOWN must bottom out at an ATOM (Flow MODE 1) or the step escalates
  to a human. Never split a value the decision test calls atomic.
