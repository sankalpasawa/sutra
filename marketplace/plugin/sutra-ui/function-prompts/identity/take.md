How to judge a request: go, ask or refuse.

## recognise

Recognise what kind of words the owner has given. There are five kinds, and only five:
task: "do X for me". query: "tell me Y". directive: "from now on, do Z", a standing change to how the department works or to its goal. feedback: "that was wrong", about work already made. new-idea: "I want a new capability", something the department cannot do today.
THE GOAL: {{goal}}
THE WORDS: {{words}}
READ BY CODE: {{facts}}

Return ONLY a JSON object: {"journey": "task" | "query" | "directive" | "feedback" | "new-idea", "why": "one line"}.

## take

Judge one request from the owner.
THE GOAL: {{goal}}
THE RULES: {{rules}}
THE REQUEST: {{words}}
READ BY CODE: {{facts}}

Return ONLY a JSON object: {"verdict": "go" | "ask" | "refuse", "why": "one line", "unsure": [str], "rule": {"line": str, "tag": "always" | "refuse" | "ask"} | null, "thin": bool}.
go: do it. ask: it reaches outside what the department makes (money, a message to someone, a change to the goal), so the owner stamps first. refuse: it breaks a rule. Reading the web is not outside: the department can read any page.
unsure: facts the request says the owner is not sure of, in a few words each; [] when none.
rule: a standing rule the request states (always or never, from now on) with its tag; null when it is one piece of work.
{{completeness}}

## answer

Answer the owner's question from the record below, and from nothing else. If the record does not hold the answer, say so.
THE QUESTION: {{question}}
THE RECORD:
- {{record}}

Return ONLY a JSON object: {"answer": str, "source": "which line of the record", "confidence": "high" | "moderate" | "low" | "unknown"}.

## rule

The owner has given a directive. Restate it as one rule, in one line, in plain words.
THE GOAL: {{goal}}
THE RULES TODAY: {{rules}}
THE DIRECTIVE: {{words}}

Return ONLY a JSON object: {"tag": "always" | "ask" | "refuse" | "goal", "line": str, "scope": "standing" | "one-time"}. tag goal: the directive changes what the department is for. scope one-time: the owner means this once.

## weigh

The owner has given feedback on work the department made. Read what it changes.
THE PAGES: {{pages}}
THE FEEDBACK: {{words}}

Return ONLY a JSON object: {"about": "the page's slug, or null", "what": "format" | "content" | "tone" | "scope" | "accuracy", "now": "the correction to make now, one line", "future": "a rule to carry forward to work like this, one line, or null"}.

## gate

An engine asks whether it may start.
THE RULES: {{rules}}
THE ENGINE: {{engine}}

Return ONLY a JSON object: {"verdict": "admit" | "wait" | "refuse", "why": "one line"}.
