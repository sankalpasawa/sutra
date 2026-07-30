# Flow Ledger

Close-stage measure/learn store for the Flow spine. Every completed unit of
work appends exactly one JSON row to `<repo-root>/.sutra/flow-ledger.jsonl`.
The ledger is the durable record of what was measured and learned at CLOSE,
and it feeds the Estimation Engine (estimate-vs-actual calibration).

Writer: `sutra/marketplace/plugin/bin/flow-ledger-append.sh`

## Row schema (`"schema": "flow-ledger-v1"`)

| Field    | Type   | Meaning                                            |
|----------|--------|----------------------------------------------------|
| `unit`   | str    | One-line statement of the unit of work             |
| `steps`  | int    | Resolved step count for the unit                   |
| `atoms`  | list   | Per-atom objects: `atom_id`, `status`, `verify_result` |
| `agents` | int    | Number of agents dispatched for the unit           |
| `close`  | object | `measured` (runnable check result), `learned` (one note), `next` (named next action) |
| `ts`     | str    | ISO-8601 UTC, stamped by the writer (`date -u`)    |
| `schema` | str    | Always `flow-ledger-v1`, stamped by the writer     |

Validation is loose: known keys are type-checked (warn, not reject); extra
keys pass through. Rows that fail JSON parse are rejected (exit 3) and
nothing is appended.

## Redaction rules

Applied to every string value, anywhere in the row, BEFORE truncation.
Matches are replaced with `[REDACTED]`:

| Pattern                        | Covers                       |
|--------------------------------|------------------------------|
| `sk-[A-Za-z0-9]{8,}`           | OpenAI/DeepSeek-style keys   |
| `AKIA[0-9A-Z]{16}`             | AWS access key ids           |
| `ghp_[A-Za-z0-9]{20,}`         | GitHub personal tokens       |
| `xox[baprs]-[A-Za-z0-9-]{10,}` | Slack tokens                 |
| `-----BEGIN [A-Z ]*KEY-----`   | PEM private key headers      |
| `Bearer [A-Za-z0-9._-]{15,}`   | Bearer auth headers          |

Keys are not scanned, only string values. Do not put evidence text in keys.

## Cap rules

1. Every string field is truncated to 2048 chars with suffix
   `...[truncated]`.
2. If the serialized row still exceeds 8192 bytes: evidence-like optional
   keys are dropped at any nesting level (`evidence`, `verify_output`,
   `log`/`logs`, `raw`, `detail`/`details`, `output`, `stdout`, `stderr`,
   `transcript`), string caps re-apply at 512 chars, and the row gains
   `"degraded": true`.
3. Last resort (still over 8192): only required keys survive
   (`unit`, `steps`, `agents`, `close`, `ts`, `schema`) plus
   `atoms_dropped` count, strings hard-capped at 128 chars.

## Single-writer rule

Appends use plain `>>` with no locking. Parallel writers are NOT
supported. The orchestrator is the only writer -- workers report atom
results up; the orchestrator appends one row per unit at CLOSE.
Authority: ADR-029 (D62 orchestrator-mode bootstrap; sole-writer flow
ledger decision).

## Close checklist

Append a row only when ALL of these hold:

- [ ] All atoms complete (or explicitly marked skipped/blocked with note)
- [ ] Verify passed for each atom -- or waiver recorded in `verify_result`
- [ ] Risks surfaced in the turn output (none silently swallowed)
- [ ] Ledger row appended (writer printed `... bytes ... APPENDED`)
- [ ] Next action named in `close.next`

## Test override

`FLOW_LEDGER_PATH=<path>` redirects the append target (tests only; never
set it in production flows). Canonical smoke test:

```
FLOW_LEDGER_PATH=/tmp/test-ledger.jsonl \
  flow-ledger-append.sh --json \
  '{"unit":"probe sk-abcdefghijklmnop","steps":1,"atoms":[],"agents":0,"close":{"measured":"m","learned":"l","next":"n"}}'
grep -q REDACTED /tmp/test-ledger.jsonl          # must pass
grep -q sk-abcdefghijklmnop /tmp/test-ledger.jsonl && echo LEAK  # must print nothing
```
