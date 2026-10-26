How Priority answers a proposal: said yes, asked for less, or said no.

## line

Adaptation proposes the workflows this department runs to reach its goal, {{source}}:
{{engines}}
WHAT EACH COSTS: up to {{calls}} calls and {{usd}} USD a day.
ROOM FOR THIS MANY WORKFLOWS: {{room}} (the limit is {{limit}})
WHAT THE LINE IS LIKELY TO COST, from what each has cost before: {{estimate}}
WHAT REMAINS OF TODAY'S ROOM AFTER IT: {{remaining}}

accept: grant them all. counter: grant only some, and name which to keep, in order. reject: grant none. Give your reason in money and room, from the figures above.
Return ONLY a JSON object: {"answer": "accept" | "counter" | "reject", "why": "one line", "keep": [names]}.

## engine

Adaptation proposes an engine for this department, from an idea the owner floated.
THE ENGINE: {{engine}}
WHAT IT DOES: {{does}}
WHAT IT NEEDS: {{needs}}
WHAT IT COSTS: {{calls}} calls and {{usd}} USD a day, the envelope of one more work engine
ROOM IN THE ENVELOPE TODAY: {{room}}

Return ONLY a JSON object: {"answer": "accept" | "reject", "why": "one line"}.

## cost

Adaptation proposes something that costs.
THE PROPOSAL: {{word}}, for the step {{step}}
WHAT IT COSTS: {{cost}}
ROOM IN THE ENVELOPE TODAY: {{room}}

Return ONLY a JSON object: {"answer": "accept" | "reject", "why": "one line"}.
