# Native scripts

Operator-facing scripts that ship with the plugin.

## `dogfood-time-to-value.ts`

Walks the canonical first-time-user journey end-to-end and emits structured wall-clock measurements per gate. Closes PS-13 ("first-time user time-to-value ≤30min on fresh install") with a measured G-1a-via-G-6 number.

### Usage

```bash
# Real-clock dogfood (operator measurement; closes PS-13)
npx tsx scripts/dogfood-time-to-value.ts

# Library mode (M11 CI variant uses this with stubInstall=true)
import { runDogfood, I_11_THRESHOLD_MS } from './scripts/dogfood-time-to-value.ts'
const result = await runDogfood({ stubInstall: true })
```

### Gates

| Gate | Label |
|---|---|
| G-0 | Clean-state baseline established |
| G-1a | Marketplace install path (closes PS-13) |
| G-1b | npm install (internal diagnostic only) |
| G-2 | Engine barrel imports without throw |
| G-3 | Vinit fixture constructable (Domain + Charter + Workflow + Execution) |
| G-4 | Workflow executes through `executeStepGraph` to terminal_state=success |
| G-5 | Observable artifact written to `.enforcement/dogfood-<runid>/result.json` |
| G-6 | Total wall-clock (verdict PASS if ≤30min; FAIL otherwise) |

### Output

JSONL stream to stdout — one record per gate:

```json
{"gate":"G-0","label":"clean-state baseline established","ts":1714500000000,"ms_since_start":0}
{"gate":"G-1a","label":"marketplace install (sutra@asawa-marketplace)","ts":1714500000050,"ms_since_start":50,"notes":"in-tree ..."}
...
{"gate":"G-6","label":"total wall-clock (verdict PASS; PS-13 CLOSED)","ts":1714500000350,"ms_since_start":350,"notes":"total_ms=350 threshold_ms=1800000"}
```

Plus a final summary block to stdout:

```
# DOGFOOD SUMMARY
# runid=1714500000000-123
# total_ms=350
# threshold_ms=1800000
# verdict=PASS
# ps_13_status=CLOSED
# artifact=.enforcement/dogfood-1714500000000-123/result.json
```

Exit code: `0` on PASS, `1` on FAIL, `2` on script error.

### Options (library mode)

- `stubInstall` (default `false`) — when `true`, G-1a + G-1b emit synthetic ms_since_start without invoking real install paths. Used by the M11 CI variant so npm-install timing flake stays out of CI while engine integration (G-2..G-5) is exercised for real (per D-NS-47).
- `artifactDir` — override the default `.enforcement/dogfood-<runid>/` location.
- `silent` — suppress JSONL stdout emission (still returned in result.gates).

### Cross-references

- Plan: `holding/plans/native-v1.0/M11-dogfood.md`
- I-11 invariant: `holding/research/2026-04-29-native-d5-invariant-register.md` line 30
- PS-13 problem state: `holding/research/2026-04-29-native-problem-state.md` lines 105-110
- M9 V2 §8 Vinit fixture (this script reuses): `tests/integration/m9-vinit-e2e.test.ts`
- Codex pre-dispatch: `.enforcement/codex-reviews/2026-04-30-m11-pre-dispatch.md`
