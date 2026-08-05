# Dispatch — the new way of working (v2.65.0)

From this version, Sutra gates file changes. Every mutation must belong to a
declared unit of work. If you update the plugin and change nothing else, your
next edit will be **blocked** — that is intended, and this page is how you
work with it.

## Why

Work used to be claimed done without proof, and file changes could land
anywhere. Now a unit declares up front what it will touch and what will prove
it worked, and the tool call is blocked if a change falls outside that.

## The three commands

Before touching a file, run these in order:

```bash
sutra-dispatch resolve --unit <name> --class <1-5> --touches <path>... \
                       --skill <none|<skill-name>|SEARCH|CREATE> [--skill-reason "..."]
sutra-atom open --goal "<observable outcome>" \
                --verify-template <file-exists|grep-count|named-test> --verify-arg <...> \
                --touches <path>...
sutra-dispatch bind --atom-id <id-printed-by-open>
```

Then do the work. Then:

```bash
sutra-atom close <id>      # runs your declared check; refuses if it fails
```

The CLIs ship with the plugin at `${CLAUDE_PLUGIN_ROOT}/bin/`.

## What each part means

| Flag | What it is |
|---|---|
| `--unit` | a name for this piece of work |
| `--class` | 1 mechanical to 5 hardest; picks the model tier |
| `--touches` | every path this unit may change. Anything else is blocked |
| `--skill` | which reusable skill governs this. `none` is allowed but needs `--skill-reason` |
| `--verify-template` | the check that proves the goal. Declared BEFORE the work, run at close |

`--touches` takes a directory as `src/` — which covers everything strictly
under it, not the directory node itself — or an exact file path.

## When you get blocked

The message names the reason. The two common ones:

**"no dispatch record"** — you have not run `resolve` and `bind` yet.

**"target X outside frozen dispatch envelope"** — the path is not in your
declared `--touches`. Two possibilities, and they are different:

1. The unit legitimately needs that path. Re-run `resolve` with it included,
   then `bind` again. This is normal and expected.
2. The change does not belong to this unit. Close the unit, start another.

Never widen an envelope purely to make a block go away — that discards the
guarantee the mechanism exists to provide.

## Honest warnings

**The command scanner produces false positives.** It reads shell command text
to find mutation targets and sometimes flags things that are not paths.
Seventeen such classes were found and fixed during development, and the rate
had not reached zero when this shipped. If you get a block you believe is
wrong, it probably is — report it with the exact command rather than working
around it, and it becomes a fixed case.

**Escalation is untested in production.** The model-escalation ladder passes
its tests but has never fired in real use.

**The dispatch record is one slot per session.** Parallel subagents each
running `resolve` will overwrite each other. Run them sequentially or in
isolated worktrees until per-agent slots land.

## Turning it off

```bash
touch ~/.atom-floor-disabled        # the atom requirement
touch ~/.dispatch-gate-disabled     # the envelope check
```

Both are founder-level decisions, not routine escapes. If you are reaching for
them daily, the false-positive rate is the bug — say so.

## Seeing what happened

```bash
${CLAUDE_PLUGIN_ROOT}/bin/dispatch-report.sh
```

Prints review candidates: possibly over- or under-powered routings, plus one
red line — a file change with no attributable unit. It never changes anything
by itself; a human reads it and decides.
