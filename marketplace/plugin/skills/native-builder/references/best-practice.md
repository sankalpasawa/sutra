# How a skill is written — the published contract, checked 2026-09-23

**status**: v1, 2026-09-23 · **owner**: Native Builder · **read when**: you are writing or changing any skill, including this one. Everything here was read from the official documentation on the date above, with the source on each row. Where the two doc sets disagree, both positions are given.

## Contents

1. Where a skill lives, and what its frontmatter must carry
2. Progressive disclosure, and the size rules
3. The description that actually fires
4. When to ship a script instead of instructions
5. What is supported for skills calling skills or agents, and what is not
6. Evals, and the minimum suite
7. The mistakes the docs call out
8. What is different inside a plugin

## 1. Where a skill lives, and its frontmatter

| Scope | Path |
|---|---|
| Personal | `~/.claude/skills/<name>/SKILL.md` |
| Project | `.claude/skills/<name>/SKILL.md` |
| Plugin | `<plugin>/skills/<name>/SKILL.md`, at the plugin root, never inside the manifest folder |

The two doc sets disagree on what is required. The runtime treats `name` and `description` as optional, falling back to the directory name and the first line of the body. The portable spec makes both required, caps `name` at 64 characters of lowercase letters, numbers and hyphens, and caps `description` at 1024 characters.

**Rule for this plugin: always write both, to the stricter limits.** It costs nothing and keeps the skill portable. In a plugin it is not optional in practice either: without `name`, the invocation name falls back to the install directory, which carries the version string and changes on every update.

Only the metadata is preloaded, about a hundred tokens per skill. The body loads when the skill fires; bundled files load only when read.

## 2. Progressive disclosure, and the size rules

| Level | When it loads | What belongs there |
|---|---|---|
| Metadata | always | name and description |
| Body | when the skill fires | the contract, the loop, the tables |
| References | when read | the detail, one domain per file |
| Scripts | when run | code, whose text never enters context |

Documented limits and why they exist:

- Keep the body **under 500 lines**. Once loaded, a skill's content stays in context across turns, so every line is a recurring cost.
- Point at references with **plain relative Markdown links**, forward slashes only.
- Keep references **one level deep**. A reference that points at another reference gets previewed with a partial read instead of read whole.
- A reference over 100 lines needs its own table of contents.
- Organise references by domain, so an unrelated domain costs nothing.

## 3. The description that fires

Third person, what it does plus when to use it, with the words a person would actually type. Never first or second person: the description is injected into the system prompt, and mixed point of view measurably hurts discovery. Gerund names read better than noun names, and `helper`, `utils` and `tools` are called out as bad names.

The shape the docs use in their own examples: a sentence of capability, then "Use when …" with concrete triggers, then, if it matters, what it is not for.

## 4. When to ship a script

Ship a script when the operation is fragile, repetitive or must come out the same every time. Write instructions when several approaches are valid and judgement is the point. A script's code never enters context, only its output.

Reference scripts by variable, not by a relative path: the skill's own directory, or the plugin root, both of which the runtime provides. Anything that must survive a plugin update belongs in the plugin's data directory, not beside the code. In a skill's script: handle errors inside the script, justify every timeout and retry rather than leaving a bare number, and validate loudly.

## 5. Skills calling skills or agents

This is the item worth being exact about, because it is easy to assume.

| Capability | Status |
|---|---|
| A skill running in a forked subagent | supported, through the fork and agent frontmatter fields; the fork sees no conversation history, so the skill must stand alone |
| A subagent preloading skill content | supported, by naming skills in the subagent's own frontmatter |
| A subagent invoking skills while it runs | supported, through the Skill tool, and removable by taking that tool away |
| **One skill invoking another skill** | **not documented.** No page states that it is supported, and none states that it is forbidden |

**So this skill's routing table is a map for the session, not a call graph.** It says which existing skill governs a phase; the session invokes it. Nothing in this plugin should depend on a skill body being able to call another skill.

## 6. Evals, and the minimum suite

The doctrine is to build the evals before writing the documentation: run the task with no skill, write down where it fails, and build cases against those gaps. Measure two different things — whether the skill *fires* on natural phrasing, and whether the *output* is right when it does.

A minimum suite for one skill is one case and two graders:

```
evals/<case-name>/
  prompt.md              the request as a person would type it, never naming the skill
  graders/
    criteria.md          type llm: PASS if <...>, FAIL if <...>
    skill-fired.md       type tool_used, tool Skill, matching the skill's name
```

Run it from the plugin root. Defaults are three runs per arm, with and without the plugin. The diagnostic that matters most: if the two arms score the same and the fired-grader fails, the **description** is wrong, not the body.

## 7. The mistakes the docs call out

| # | Mistake | What it costs |
|---|---|---|
| 1 | a vague description, or first or second person | the skill never fires |
| 2 | a verbose body explaining what the model already knows | a recurring token cost on every later turn |
| 3 | nested references | the model previews instead of reading |
| 4 | time-sensitive wording | it goes stale and misleads |
| 5 | inconsistent terminology for one thing | harder to follow, and drifts |
| 6 | four options where one default belongs | confusion, no default behaviour |
| 7 | backslash paths | breaks off Windows |
| 8 | assuming packages are installed | fails at run time |
| 9 | scripts that defer their errors to the model | unreliable, and unexplainable |
| 10 | testing in the session that wrote it | leftover context hides the gaps; use a fresh session |

## 8. Inside a plugin

- Skills live at the plugin root under `skills/`, never inside the manifest folder. Putting components in the manifest folder is called out as a common mistake: they are simply not found.
- The invocation name is namespaced by the plugin, so always set `name`.
- **A version bump is needed when the plugin declares a version**, which this one does: users receive changes only on a bump, and the old version lingers in their cache for about two weeks. Locally, `/reload-plugins` picks changes up in-session.
- Validate before shipping, and prefer the strict mode in a pipeline.

---
provenance: {author: claude, date: 2026-09-23, session: 8e2713c3, inputs: [the official Claude Code skills, plugins, plugin-evals and sub-agents documentation and the portable Agent Skills spec, fetched 2026-09-23 by a research agent that cited each claim], review: the researcher flagged one hallucinated section in a fetch summary and discounted it; item 5 above reflects that correction, confidence: high on 1 to 4 and 6 to 8; item 5 is a documented absence, not a documented prohibition}
