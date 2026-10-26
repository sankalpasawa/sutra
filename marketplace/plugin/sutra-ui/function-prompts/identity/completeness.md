When the department has enough to work; what to ask if not.

## thin

thin: true when the request names nothing to build from (no subject, no purpose).

## enough

Read who the department is against Identity's standard, and say whether it is enough to start work on. The standard has five points, and only five:
goal: the goal names what the department makes and for whom.
items: done-when is a list of items, and each item says how it is checked.
rules: every rule is tagged go, ask, refuse or always.
owner, budget: the department has an owner and a budget.
invented: nothing is invented; a fact the owner did not give is marked to confirm, never stated.
THE OWNER'S WORDS: {{words}}
WHAT ROOT ASKED, AND WHAT THE OWNER SAID: {{asked}}
THE GOAL: {{goal}}
DONE WHEN: {{items}}
THE RULES: {{rules}}
THE OWNER: {{owner}}
THE BUDGET: {{budget}}
TO CONFIRM: {{confirm}}

Ask only for what is missing, in one plain question to the owner, the most important first. Never ask what the owner's words or Root's questions already answered.
Return ONLY a JSON object: {"enough": bool, "missing": ["goal" | "items" | "rules" | "owner" | "budget" | "invented"], "question": "one question, or an empty string when enough", "why": "one line"}.
