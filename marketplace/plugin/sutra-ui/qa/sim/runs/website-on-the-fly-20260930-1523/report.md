# Run 5, run 4 (misdirected): the Beta rerun under the baseline's organisation name

| Field | Value |
|---|---|
| **status** | 2026-09-30 15:23 IST, Sutra Beta 2.306.21-beta.1 (8331); stopped after one row |
| What happened | the driver founded "Hampi Guide" again on a record that held it since run 1; the app found the existing Root (created: false) and handed the words to the old website department ("handed to Hampi Guide Website", "filed in the Brief"), which is the front door's right behaviour; the driver then watched the first child under that Root, the old website department, so nothing it read could show the on-the-fly line |
| Finding | 61, driver: a rerun on a shared record needs a fresh organisation name (run5.py now takes RUN5_ORG and refuses an organisation that already exists); not an app finding. The old department was stopped (POST /stop) so the handed words cost no second build |
| Next | run 5 (`website-on-the-fly-<stamp>`) under "Hampi Trip Planner" on the same Beta |

provenance: {author: claude, session: 17842ce0, date: 2026-09-30, inputs: [ledger.jsonl (1 row), the Root's chat on 8331], review: none, confidence: high}
