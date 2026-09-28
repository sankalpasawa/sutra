# Runs of the Human Simulation

One folder per run: `runs/<goal>-<yyyymmdd-hhmm>/`.

| File | Holds |
|---|---|
| `ledger.jsonl` | one row per action: `{"n", "at", "why", "did", "where", "saw"}`; `why` is the person's reason in his words |
| `findings.jsonl` | one row per miss: `{"outcome", "expected", "seen", "capture", "kind": "app" or "expectation", "why_it_matters"}` |
| `report.md` | N of M outcomes, K of L variances, the findings, the time; what the person got |
| `*.png` | one capture per outcome checked, named by the outcome id |

Runs are kept in the repo only when they are the record of a finding or a release; the rest stay local (`runs/*/` is ignored except README.md and the runs named in a TODO row).

provenance: {author: claude, session: 17842ce0, date: 2026-09-28, inputs: [AGENT.md], review: none, confidence: high}
