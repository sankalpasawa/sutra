# What a component owes

**status**: v1, 2026-09-23 · **owner**: System engineering · **read when**: you have found a component boundary and are about to write what it does.

A component that makes things owes seven answers before it is built. Anything missing here becomes a surprise at the twentieth instance.

## The seven

| # | Field | The question it answers | Fails as |
|---|---|---|---|
| 1 | **Makes** | what kind of thing comes out, exactly one kind | a component that makes two kinds is two components |
| 2 | **Takes** | the smallest input that could work | a wide input hides the fact that nobody knows the shape yet |
| 3 | **May write** | what it changes without asking, named by place | "it writes what it needs" is how a generator becomes an incident |
| 4 | **Must ask** | what it can only propose, for a person to stamp | the list is short and absolute; the record is the boundary |
| 5 | **Returns** | what the caller gets, including on partial success | a return of nothing means the caller guesses |
| 6 | **On failure** | stop, retry with a budget, or leave a half-made thing and say so | silence is the worst of the three |
| 7 | **Proof** | the check that refuses a malformed instance | without it, the guarantees are a comment |

## Writing them down

Keep it to one block. If it does not fit, the component is too big.

```
MAKES:      one function template for a department
TAKES:      the function, the parent template, the lines to add
MAY WRITE:  the template file under its own folder
MUST ASK:   any change to a department's own record
RETURNS:    the template id, and the parent it derived from
ON FAILURE: refuses and names the line that broke the law; writes nothing
PROOF:      the suite: a child keeps every parent line and adds at least one
```

## The seam, stated properly

The most valuable line in the contract is **must ask**. It is what keeps a generator from becoming an unreviewable actor. In this model the seam is already fixed: a component may write inside its own folder, and every change to a record goes through an ask a person stamps. A new component that wants a wider seam is not a design question, it is a founder question.

## Three failures worth naming

| # | Failure | What it looks like later |
|---|---|---|
| 1 | The component writes what it likes | nobody can say which instances were reviewed |
| 2 | The component returns only success or failure | the caller cannot tell a no-op from a build |
| 3 | The proof lives in the component, not beside the instances | the guarantee holds only for things made by that code path, and the first hand-made instance breaks it silently |

The third is the subtle one. **Put the proof where the instances are**, so a thing made by hand is judged by the same check as a thing made by the component.

## Versioning an instance

Every instance needs to answer, a year later: what made me, from which parent, and when. Three fields, written at creation, never inferred:

| Field | Why |
|---|---|
| made by | which component and which version |
| derived from | the parent, if the growth law has parents |
| made at | so a run can be matched to a change |

---
provenance: {author: claude, date: 2026-09-23, session: 8e2713c3, inputs: [the function-templates contract and its suite, the builders page's contract floor, the retire verb's disposition behaviour], review: none by a second model, confidence: high; each failure listed was observed in this system, not imagined}
