How Audit reads what went live against what was asked.

## judge

Check what the department made against what it was asked. Read the brief and what the department's own engines filed, then the pages. Find any statement of fact on a page that neither the brief nor a filed artifact gives: a phone number, an address, a date, a count, a name, a claim of history. A fact a filed artifact gives, with its source, is backed: do not report it. Return ONLY a JSON object: {"ok": bool, "findings": [{"page": str, "claim": str, "severity": "high" | "low"}]}. high: a reader could be harmed or misled by it. At most eight findings.

THE BRIEF:
{{brief}}{{filed}}

THE PAGES:
{{pages}}
