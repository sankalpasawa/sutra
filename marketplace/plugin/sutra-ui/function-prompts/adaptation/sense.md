How Adaptation reads an idea the owner floats: what it asks, and the shapes it could take.

## shape

The owner floats an idea the department cannot do today. Do not plan a build. Reflect the idea back in sharper words, name the question underneath it, and give two or three shapes it could take, smallest first. Then say what engine would do it each time on its own: pick one from the Library below when its use case fits (pick), else shape one (engine: a name of one or two words, what it does in one line, and what it needs from this list: {{needs}}); both null when the idea asks for no engine.
THE GOAL: {{goal}}
THE IDEA: {{idea}}
ENGINES IN THE LIBRARY, NOT YET IN THIS DEPARTMENT: {{library}}

Return ONLY a JSON object: {"reflected": str, "question": str, "shapes": [str, str, str], "pick": str or null, "engine": {"name": str, "does": str, "needs": [str]} or null}.
