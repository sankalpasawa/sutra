# Sutra — A/B Test Framework

Every client company can test whether Sutra's OS improves their outcomes. This is how Sutra earns its place — with data, not with faith.

## The Test

Any client can run a controlled comparison:
- Some features built WITH Sutra OS (full process)
- Some features built WITHOUT (direct/vibing)
- Same metrics measured for both
- Data decides whether Sutra adds value

## Setup (for any client)

### 1. Define the experiment
```
Features in test: [5 recommended minimum]
Split: alternating (1-HIGH, 2-LOW, 3-HIGH, 4-LOW, 5-tiebreaker)
Duration: until all features shipped
```

### 2. Metrics to collect per feature
| Metric | How to measure |
|--------|---------------|
| **Ship time** | Clock hours from "start" to "on device/deployed" |
| **Break rate** | Count of bugs introduced by this feature |
| **Rework cycles** | Times the feature needed re-doing after "done" |
| **Design quality** | Design QA score (0-10 or pass/fail on sensor checks) |
| **Knowledge captured** | Did we learn something that updates the knowledge system? (yes/no) |

### 3. Run the features
- High-depth features follow the full OS: shape → design → specify → build → verify → learn
- Low-depth features follow minimal process: read knowledge system → build → ship
- Log metrics honestly. Don't optimize for one mode over the other.

### 4. Analyze results
```
High-depth features average:
  Ship time: ___
  Break rate: ___
  Rework: ___
  Quality: ___
  Knowledge: ___

Low-depth features average:
  Ship time: ___
  Break rate: ___
  Rework: ___
  Quality: ___
  Knowledge: ___
```

### 5. Decision
| Result | Action |
|--------|--------|
| Higher depth faster AND fewer breaks | Use higher depth as default |
| SUTRA slower but significantly fewer breaks | Use adaptive depth (higher for risky, lower for small) |
| Lower depth faster AND same break rate | Strip Sutra back. It's overhead. |
| Mixed / unclear | Run 5 more features |

## What Sutra Learns from A/B Results

Every client's A/B test results feed back to Sutra:

**If higher depth wins:**
- Which steps added the most value? (usually: specify + verify)
- Which steps were overhead? (maybe: formal shape for small features)
- Optimize: keep the valuable steps, trim the overhead

**If lower depth wins:**
- Sutra's process is too heavy for this stage/company
- Simplify: fewer steps, lighter checkpoints
- Maybe this client needs a different Sutra module (startup vs growth vs enterprise)

**If adaptive depth is the sweet spot:**
- Refine the size thresholds (what counts as small vs medium vs large)
- Document which change types benefit from process and which don't

## Meta-Learning

Across multiple clients, Sutra tracks:
- Which company stages benefit most from full OS? (hypothesis: growth stage > pre-launch)
- Which functions benefit most from structure? (hypothesis: cross-cutting > single-function)
- What's the minimum viable process that still prevents breaks?

This data makes Sutra better for every future client.
