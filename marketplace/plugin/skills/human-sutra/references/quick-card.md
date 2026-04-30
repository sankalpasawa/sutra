# H↔Sutra Layer — Quick Card (v1.0)

One-page printable reference. Charter: `sutra/os/charters/HUMAN-SUTRA-LAYER.md`. ADR-001: `sutra/os/decisions/ADR-001-h-sutra-9cell-grid.md`.

---

## The 9-cell grid (3 verbs × 3 directions)

```
+------------+--------------------+--------------------+--------------------+
|            |       QUERY        |       ASSERT       |       DIRECT       |
+------------+--------------------+--------------------+--------------------+
| INBOUND    | IN-QUERY           | IN-ASSERT          | IN-DIRECT          |
| (founder   | "what is X?"       | "you missed Y"     | "do X" / "build it"|
|  -> Sutra) |                    |                    |                    |
+------------+--------------------+--------------------+--------------------+
| INTERNAL   | INT-QUERY          | INT-ASSERT         | INT-DIRECT         |
| (Sutra <-> | subagent asks main | codex verdict /    | main dispatches    |
|  Sutra)    | for context        | subagent result    | subagent           |
+------------+--------------------+--------------------+--------------------+
| OUTBOUND   | OUT-QUERY          | OUT-ASSERT         | OUT-DIRECT         |
| (Sutra ->  | CLARIFY            | INFORM / DISAGREE  | ASK-LATER /        |
|  founder)  |                    | / ACK              | HANDOFF / CASCADE  |
+------------+--------------------+--------------------+--------------------+
```

Verbs: **QUERY** (read) · **ASSERT** (declare fact / claim) · **DIRECT** (request action).

---

## The 3 tags (orthogonal)

```
TENSE     past | present | future        (what content references)
TIMING    now  | later   | recurring     (when execution happens)
CHANNEL   in-band | out-of-band          (outbound delivery surface)
```

---

## REVERSIBILITY (execution metadata, NOT a 4th tag)

```
reversibility   reversible | irreversible    (denylist match -> irreversible)
decision_risk   low | medium | high           (sensitive-domain keywords)
```

Captured per turn. Gates safety rules. NOT part of the tag triple.

---

## Irreversible-domain denylist (6 categories)

For these, "proceed with assumption" is **forbidden** — route to refuse-and-re-prompt:

1. **Destructive file ops** — `rm -rf`, `git reset --hard`, `git push --force`, mass-delete, mass-rename
2. **External sends** — Resend / email / Slack / Discord / SMS / push notifications crossing founder->external boundary
3. **Founder-reputation outputs** — anything signed as Sankalp / Asawa / Sutra to investor, client, hire
4. **Money movement** — Stripe / wire / PSP / crypto / payroll
5. **Legal / compliance** — contracts, ToS, privacy policy, regulatory filings
6. **Irreversible publication** — git push to public repos, npm publish, Play Store / App Store release, public website publish

---

## Header tag examples (5 representative cells)

```
[INBOUND·QUERY  · TIMING:now   · CHANNEL:in-band      · REV:reversible   · RISK:low]
[INBOUND·DIRECT · TIMING:now   · CHANNEL:in-band      · REV:reversible   · RISK:low]
[INBOUND·DIRECT · TIMING:now   · CHANNEL:in-band      · REV:irreversible · RISK:high]
[INBOUND·ASSERT · TIMING:now   · CHANNEL:in-band      · REV:reversible   · RISK:low]
[STAGE-1-FAIL   · TIMING:now   · CHANNEL:in-band      · REV:reversible   · RISK:medium]
```

Format: `[<DIRECTION>·<VERB> · TIMING:<...> · CHANNEL:<...> · REV:<...> · RISK:<...>]`

---

## Bounded retry rule

After 1 CLARIFY attempt for the same turn → action depends on REVERSIBILITY × decision_risk: **reversible/low** proceed on stated assumptions · **reversible/medium** proceed + surface assumption · **irreversible/any OR denylist hit** refuse + escalate (require explicit IN-DIRECT re-prompt). Terminates the gate-fail loop.

---

## Classification precedence

```
DIRECT > QUERY > ASSERT
```

A turn carrying multiple acts: principal_act = highest-precedence verb present; the rest log as `mixed_acts`.

---

## OUT-QUERY guardrails (all 3 must hold; else demote to OUT-ASSERT)

1. Names exact missing variable (file path · A vs B · numeric value)
2. Explains why default is unsafe (gate-condition declaration)
3. One-turn-answerable (yes/no · A/B/C · a name · a path)
