How Audit reads what went live against what was asked.

## judge

Check what the department made against what it was asked. Read the brief and what the department's own engines filed, then the pages. Find any statement of fact on a page that neither the brief nor a filed artifact gives: a phone number, an address, a date, a count, a name, a claim of history. A fact a filed artifact gives, with its source, is backed: do not report it. Return ONLY a JSON object: {"ok": bool, "findings": [{"page": str, "claim": str, "severity": "high" | "low"}]}. high: a reader could be harmed or misled by it. At most eight findings.

THE BRIEF:
{{brief}}{{filed}}

THE PAGES:
{{pages}}

## items

Read the work against what was asked, one done-when item at a time. For each item below give a verdict: met only when the work itself shows it; not met when the work leaves it out or shows it does not hold; to confirm when it rests on a fact only the owner can give, or the work cannot show it either way. Say in one line what is or is not true (the claim) and in one line what in the work shows it (the evidence). What code measured is given below: weigh it, and never call an item met that a measure shows failing.
Return ONLY a JSON object: {"items": [{"id": "D1", "verdict": "met" | "not_met" | "to_confirm", "claim": "what is or is not true, one line", "evidence": "what in the work shows it, one line"}], "findings": [{"where": str, "claim": str, "severity": "high" | "medium" | "low", "item": "D1" or null}]}.
One row for every item, each under its own id, and no other row. A finding is something to put right that you saw while reading: say where it is and what is wrong, and name the item it belongs to, or null. high: a reader could be harmed or misled by it. Never guess a fact that neither the brief nor a filed artifact gives: a phone number, an address, a date, a count, a name. A fact a filed artifact gives, with its source, is backed: do not report it. At most eight findings.

THE BRIEF:
{{brief}}{{filed}}

THE DELIVERABLE:
{{deliverable}}

THE DONE-WHEN ITEMS:
{{items}}

WHAT CODE MEASURED:
{{measured}}
