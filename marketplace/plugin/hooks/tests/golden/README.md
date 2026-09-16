# Golden hook corpus

**Status**: active
**Owner**: CEO of Sutra
**Updated**: 2026-09-16
**Tool**: `bin/sutra-charcap` (v1.7.2)
**Plan**: `holding/plans/sutra-runtime/EXECUTION.md` step 7

This directory is the recorded behaviour of the legacy bash hook fleet. It exists
so the runtime rewrite can prove "same behaviour" instead of asserting it. Every
file here was produced by `sutra-charcap record`; nothing is hand-written except
`stdin.json`, `env` and `fs/`.

<a id="layout"></a>
## 1. Layout

| Path | Written by | Contents |
|---|---|---|
| `families.json` | `sutra-charcap derive-families` | family -> `{event, scripts[]}` in hooks.json registration order |
| `README.md` | hand | this file |
| `<family>/cases/<case-id>/stdin.json` | hand | one realistic hook input |
| `<family>/cases/<case-id>/env` | hand | `KEY=VAL` lines, one per line |
| `<family>/cases/<case-id>/fs/` | hand | files materialised into the fresh project root |
| `<family>/cases/<case-id>/expect/<script>.stdout` | record | normalised stdout |
| `<family>/cases/<case-id>/expect/<script>.stderr` | record | normalised stderr |
| `<family>/cases/<case-id>/expect/<script>.exit` | record | exit code, one line |
| `<family>/cases/<case-id>/expect/<script>.fx` | record | file-effect list (see s4) |
| `<family>/cases/<case-id>/expect/ORDER` | record | the slug order, one per line (absent when the case is NO-MATCH) |
| `<family>/cases/<case-id>/expect/NO-MATCH` | record | why NO registration of this family runs for this case (see s1b) |
| `<family>/cases/<case-id>/EVENT` | hand | optional; the hook event to dispatch when `stdin.json` cannot name one |
| `<family>/KNOWN-DEFECTS.md` | hand | behaviour that is recorded but wrong; also the only way an all-127 recording may be written (s3) |

`<script>` is the effective hook file's basename. A script registered twice in
the same family keeps both recordings: the repeat gets a `~1`, `~2` suffix. A
slug is allocated over the whole family, so it names the same registration in
every case, whether or not that case runs it.

<a id="matcher"></a>
### 1a. A case records only the scripts the host would run

Each registration in `hooks.json` carries a matcher and the host runs it only
when the matcher matches the event's `tool_name`. The corpus follows the same
rule: `record` and `verify` run, for one case, only the family's registrations
whose matcher matches THAT case's `tool_name`, and `expect/ORDER` is exactly
that per-case list.

The rule is the HOST's, read from `runtime/pipeline.json` `.matcher_semantics`
(`anchored-ere`); any other value aborts the tool rather than letting it guess.
One rule, no special case for a plain alternation:

| Matcher form | Example | Matches |
|---|---|---|
| omitted, empty, `*` or `null` | `*` | every tool, and events with no tool at all |
| anything else | `Edit\|Write`, `mcp__.*` | the WHOLE `tool_name` matches `^(matcher)$` as a POSIX ERE |

So `Edit|Write` does NOT match `MultiEdit`, and the `permission` registration
`Bash|...|mcp__.*|...` DOES match `mcp__claude_ai_Gmail__send_message`. The
recorder, the legacy verifier and the `sutra-turn` projection all call the same
`matcher_matches()`, so a case can never be recorded with a step set the host
and `sutra-turn` would not produce.

A case whose `stdin.json` carries no `tool_name` (UserPromptSubmit,
SessionStart, Stop, a malformed payload) matches only the `*` form - an anchored
ERE has no name to test. So `pretool-gates` records 24 scripts for a `*`-only
case but 16 for a `Write` case. `verify` recomputes the list and fails loudly
when `expect/ORDER` no longer matches it, which is the signal to re-record the
family.

Registrations of the mixed-event `lib` family are selected by the case's EVENT
first and by the matcher second: the host only dispatches the registrations of
the event it is running.

<a id="no-match"></a>
### 1b. `NO-MATCH` - zero registrations is an expectation

"Nothing ran" and "nothing was recorded" must not look alike. A case that
selects zero registrations gets NO `expect/ORDER`; it gets `expect/NO-MATCH`
naming the `tool_name`, the event, the matcher semantics and every registration
that rejected it (by matcher, or by event for a mixed family). Both runners are
held to it:

| Runner | What NO-MATCH means |
|---|---|
| `legacy` | the file is re-derived and diffed; a surviving `ORDER` next to it, or a missing `NO-MATCH` while registrations now match, is a FAIL |
| `sutra-turn` | the runner must execute ZERO registrations of this family, and - when the whole event selected nothing - emit nothing at all |

Current NO-MATCH cases: `permission/malformed-json` (no `tool_name`, and the one
PermissionRequest registration matches a name list).

<a id="inputs"></a>
## 2. What a case supplies

`stdin.json` is a realistic hook payload: `session_id`, `hook_event_name`, `cwd`,
`transcript_path` pointing at a small fixture transcript inside `fs/`, and then
`prompt` (UserPromptSubmit) or `tool_name` + `tool_input` (PreToolUse /
PostToolUse).

`env` holds `KEY=VAL` lines, including `CLAUDE_CODE_SESSION_ID`. It must NOT set
`CLAUDE_PROJECT_DIR` or `CLAUDE_PLUGIN_ROOT`: the tool supplies both at run time
and strips any case-supplied value, because a fresh root is created per run.

`fs/` is copied into that fresh project root before every single script runs, so
one script's writes never leak into the next script's fixture. Markers therefore
live at `fs/.claude/sessions/<sid>/<marker>`.

Three tokens are expanded inside `stdin.json` and `env` at run time: `<PROJ>`,
`<HOME>`, `<PLUGIN>` (the legacy `@PROJ@` / `@HOME@` / `@PLUGIN@` / `@HOOKS@`
spellings still expand).

<a id="hermetic"></a>
## 3. How a run is isolated

### 3a. The fresh root has a constant LENGTH, not just a fresh path

Normalisation maps the fresh root to `<PROJ>`, which handles a root that
*appears* in recorded bytes. It cannot handle a root that is *measured*: hooks
write the byte count of their stdin (`reset-turn-markers.sh:40`,
`"stdin_bytes"`) and fixed-width truncations of it (`:41` `head -c 200`, `:104`
`head -c 300`), and that stdin embeds `CLAUDE_PROJECT_DIR`. A root 8 characters
longer changes the count and shifts the truncation window, so the recording
verifies green where it was made and red from a work dir with a
different-length path - the entire "fresh-environment leak" class.

So every run root is padded to a constant length (`SUTRA_CHARCAP_ROOTLEN`,
default 160):

```
<work dir>/run/<16 hex of family|case><pppp...>/{proj,home,stub,tmp}
```

The family and case are hashed so their own name lengths cannot leak either,
and `proj` / `home` / `stub` are equal-length children. charcap dies with an
explicit message if the work dir is too long to pad to that width - a truncated
root would silently rewrite every recorded byte count.

Each run is `env -i` with: a private `HOME`, a private `CLAUDE_PROJECT_DIR`
seeded from `fs/`, `TZ=UTC`, `LC_ALL=C`, `TERM=dumb`, and a `PATH` whose first
entry is a stub directory holding no-op `claude` and `gh` shims - so a hook that
would reach the network stays offline and deterministic. A git repository with a
frozen identity is initialised in the fresh root so `git rev-parse
--show-toplevel` resolves inside the sandbox. A perl `alarm` supplies the wall
cap; macOS has no `timeout(1)`.

<a id="fx"></a>
## 4. File effects (`.fx`)

`.fx` is the sorted list of files the script created or changed under the project
root, one `<sha256>  <relative path>` per line, plus `deleted  <path>` for a
removal. `.git/` is excluded - the fixture repo is scaffolding, not effect.

The digest is taken over the file's NORMALISED bytes (s5), so a marker that
embeds a timestamp still yields a stable digest.

<a id="norm"></a>
## 5. Normalisation

Applied to stdout, stderr and to file contents before hashing.

| Volatile input | Token |
|---|---|
| the fresh project root | `<PROJ>` |
| the plugin root | `<PLUGIN>` |
| the sandbox / work root | `<SB>` |
| the fresh `HOME` | `<HOME>` |
| this corpus's own path | `<GOLDEN>` |
| ISO-8601 timestamps, `YYYY-MM-DD`, `HH:MM:SS`, 13-digit ms epochs, 10-digit epochs | `<TS>` |
| uuids | `<UUID>` |
| a number preceded by `pid` | `<PID>` |
| `NNNms`, `elapsed=N`, `took=N`, `duration=N` | `<MS>` |
| hostname, username | `<HOST>`, `<USER>` (word-bound, see 5b) |
| `x.y.z` release versions | `<VERSION>` |
| a run root cut in half by a fixed-width slice of stdin (s5a) | `<CUTPATH>` |

<a id="normorder"></a>
### 5b. Rule order and guards are part of the contract

Three pairs of rules would claim each other's text, so the ORDER they are
emitted in is the contract, not an implementation detail:

| First | Then | Why |
|---|---|---|
| uuid | the digit rules | a uuid tail is 12 hex characters; an all-digit tail would be eaten by the epoch rule |
| ISO timestamp | the bare-date rule | an ISO stamp starts with a bare date |
| dotted date `2026.09.15` | the version rule | both are `digits.digits.digits`; a dotted date is a date in every hook that prints one |

Two rules are emitted TWICE on purpose. Each consumes the character after its
match as a trailing guard, so under `/g` the second of two adjacent occurrences
on one line (`x 1.2.3 4.5.6 y`, `x asawa y asawa z`) would be left raw.

The `<VERSION>` rule's guards are deliberate: a HYPHEN on the left is a guard
(`sutra-core-2.278.0` is a version), and a trailing `.` followed by a non-digit
or end of line is accepted (`plugin v2.278.0.` normalises). A 4-part literal
(`1.2.3.4`), an IPv4 address with or without a port (`10.0.0.1:8080`),
`a.1.2.3` and `core/2.274.2/` stay raw.

The `<USER>` / `<HOST>` rules are WORD-BOUND on both sides. An unguarded rule
binds the corpus to the machine that recorded it: the founder's user name is a
substring of the `sankalpasawa/sutra-data` literal that
`sessionstart-privacy-notice.sh` prints, so an unguarded recording froze
`sankalp<USER>/sutra-data` and every machine whose `id -un` differs (a CI runner
is `runner`) replayed the literal raw and failed 22 session checks. Nothing in
the corpus or the gate skips on identity - the rules are bound so that identity
cannot matter. `families.json` carries `recorded_on` (the recording box's
`uname -s`, so a reader — and one caller — knows whether BSD or GNU tools
produced these bytes); no user or host name is shipped in the file. The one
caller is `runtime/tests/test-charcap-parity.sh`: it compares `recorded_on`
with its own `uname -s` and SKIPS on a mismatch, because replaying
BSD-recorded bytes on a GNU box diffs on platform, not on parity. Neither
runner reads the field — a replay on the recording platform behaves exactly as
before, and nothing in the corpus or the gate skips on IDENTITY (s5b), only on
platform.

`record` REFUSES (s12) any recording in which an `expect/` file still carries a
`<USER>` / `<HOST>` token glued to a word character, or a raw `x.y.z` the
version rule should have taken. That assertion, not the regex, is what keeps the
next release bump green.

<a id="cutpath"></a>
### 5a. Paths cut in half

Section 3a keeps the run root the same LENGTH everywhere. That is not enough on
its own. A hook that logs a fixed-width slice of its stdin
(`reset-turn-markers.sh:104`, `head -c 300`) can cut a path in the middle, and
the half that survives depends on how long the work dir is named: a long base
leaves `/private/tmp/claude-501/-`, a short one leaves the whole base plus
`/run/c53120bae9f9`. Both are the same number of characters and neither is a
whole path, so the s5 rules cannot see either and the recording verifies green
only where it was made.

Any PREFIX of a run root therefore collapses to one token, `<CUTPATH>`, in both
forms a cut can leave - raw when the cut fell inside the base, `<SB>/run/<key>`
plus padding when the base survived it. Each rule is guarded by a following
NON-path character (or end of line), so a whole path - which continues with a
path character - can never match one: whole paths keep `<PROJ>`, `<SB>`,
`<PLUGIN>`.

Not covered, deliberately: a cut inside the first 10 characters of a path, the
flattened (`slashes -> dashes`) twin of a cut path, and a cut landing exactly on
the work dir's last character. If a hook ever produces one, pin the value in the
case's `fs/` rather than excluding the file from the `.fx` hash.

<a id="commands"></a>
## 6. Commands

| Command | Effect |
|---|---|
| `sutra-charcap derive-families` | regenerate `families.json` from `hooks/hooks.json` |
| `sutra-charcap families` | list families, events, script and case counts |
| `sutra-charcap record --family ups` | (re)record one family |
| `sutra-charcap record --all --proj-root DIR` | record everything, fresh roots under `DIR` |
| `sutra-charcap verify --all --runner legacy` | replay the bash; exit 0 iff byte-identical |
| `sutra-charcap verify --all --runner sutra-turn` | replay through the new runtime |
| `sutra-charcap shadow --family ups --days 7` | both runners, diffs to `.sutra/shadow/ups/diffs.jsonl` |
| `sutra-charcap record --all --jobs 8` | same corpus, 8 cases at a time |

`--jobs N` (default 4) applies to `record` and to both `verify` runners. It runs
N CASES concurrently; each case still gets its own fresh project root, HOME,
TMPDIR, stub `PATH` and git fixture, and writes only into its own `expect/`
directory, so a corpus recorded at `--jobs 8` is byte-identical to one recorded
at `--jobs 1`. Verify diagnostics are buffered per case and replayed in case
order, so the failure transcript does not depend on N either. Claim checked
2026-09-11: one case and three cases recorded at `--jobs 1` then `--jobs 4`,
`diff -r` clean both times (three cases: 6 s serial, 2 s parallel).

<a id="families"></a>
## 7. Family derivation

Derived from the FULL registry, registration order preserved:
`hooks/hooks.json.step3` when it exists, else `hooks/hooks.json`. The file
actually read is recorded in the map's `source` field. After the runtime lands,
`hooks/hooks.json` is the collapsed registry (one `bin/sutra-turn` row per event
plus bare `bin/sutra-canary`), so deriving from it would rewrite this 98-row map
into a handful of runtime rows and delete the corpus's contract;
`derive-families` REFUSES a registry that names no `hooks/` script at all (s14).

| Family | Rule |
|---|---|
| `ups` | every UserPromptSubmit registration |
| `session` | every SessionStart registration |
| `pretool-gates` | PreToolUse registrations whose script has an exit-2 / deny path |
| `pretool-other` | the remaining PreToolUse registrations |
| `posttool` | every PostToolUse registration |
| `permission` | every PermissionRequest registration |
| `stop-gates` | Stop registrations that can emit a block decision or exit 2 |
| `stop-collect` | the remaining Stop registrations |
| `lib` | each `hooks/lib` helper, exercised through one caller |

<a id="turn"></a>
## 8. What `--runner sutra-turn` compares

`bin/sutra-turn run --event <E>` is invoked once per case in the same fresh root,
and **`<E>` is the CASE's event, not the family's**: `hook_event_name` from
`stdin.json` (read with `jq`, then scraped raw so a malformed payload that still
carries the field is honoured), then the case's optional `EVENT` file, then the
family's event. Per-case dispatch is the only correct behaviour for a
mixed-event family, so **no family is skipped** - `lib` is compared like every
other one. A case for which none of the three sources names a hook event is a
FAIL, not a silent skip.

The corpus is family-scoped; the runner is event-scoped. `PreToolUse` is split
into `pretool-gates` + `pretool-other` and `Stop` into `stop-gates` +
`stop-collect`, so ONE ledger covers TWO families. The comparator therefore
**projects** the ledger onto the case's `expect/ORDER`: it keeps only the rows
whose `script` belongs to this family and case, in ledger order, and diffs those
pairwise. A row that arrives out of registry order is a failure; a row for the
other family is simply not this family's business.

| Check | Applies to | Rule |
|---|---|---|
| per-step `exit` | every family | projected row vs `expect/<slug>.exit` |
| per-step stdout / stderr | every family | raw strings when the row carries them (charcap normalises), else `stdout_sha256` / `stderr_sha256` vs the sha of the recorded bytes |
| registry order | every family | projected rows appear in `ORDER` order |
| combined emit | families whose `expect/` IS the whole event | `additionalContext` joined by two newlines, first exit-2 wins, other stdout passed through |

Two families share `PreToolUse` and two share `Stop`, and `lib` holds a handful
of the registrations of three events, so for those five the emit of the whole
event is a superset of the family's `expect/` and is NOT compared - comparing it
would be a false FAIL, not a finding, and the per-step rows are what carry their
parity claim. `ups`, `session`, `posttool` and `permission` own their event
alone and do have their emit compared.

There is **no post-deny skip** in the runtime (`bin/sutra-turn`: `class` gates
EMISSION, never execution), so the old "not executed after a deny" note class is
retired. A step of the case's `ORDER` with no ledger row - or with a ledger
`skip` row - is a FAIL.

One registration can fill SEVERAL slots of a family: the four `hooks/lib`
helpers are all exercised through `hooks/dispatch-gate.sh`, so `lib`'s
`PreToolUse` cases carry `dispatch-gate.sh`, `~1`, `~2`, `~3`. The host - and
`sutra-turn` - run that registration ONCE, while `legacy` re-runs it once per
slot. The single ledger row is therefore compared against the FIRST slot of the
group; the repeat slots keep their legacy recordings and are reported as
`note ... duplicate slot(s) of an already-compared registration`.

<a id="exclusive"></a>
## 9. One work dir per run

Fresh roots are keyed by `<family>/<case>` and by nothing else, so two charcap
processes sharing a work dir run the same case in the same directory and delete
each other's tree mid-run. That does not produce a clean error - it produces
invented FAILs (a gate reads a fixture a sibling just removed and reports a
different exit; a `.jsonl` a sibling truncated hashes differently).

So the default work dir is private to the process (`mktemp -d`, removed on
exit). `SUTRA_CHARCAP_WORK` still overrides it and is then locked for the run: a
second process asking for the same dir dies instead of inventing results.
**Parity numbers quoted from a run that did not hold an exclusive work dir are
not evidence.**

<a id="envquote"></a>
## 10. The env vector is one line, one argument

Every case runs under `env -i` with the case's `env` file. That vector is built
one LINE = one ARGUMENT. Word-splitting the file (`env -i $(cat env | tr '\n'
' ')`) breaks any value that contains a space -
`stop-gates/block-context-budget` pins
`CLAUDE_TRANSCRIPT=read holding/a.md holding/b.md ...`, `env` then exec'd
`holding/a.md`, and every step of the case recorded `exit=127` with empty
output: green under `legacy` for the wrong reason, `no ledger` under
`sutra-turn`. `record` therefore also REFUSES a case whose every step exited 127
(it names the case, aborts the family and exits non-zero) unless
`<family>/KNOWN-DEFECTS.md` names the case with a reason.

There are three REFUSE classes: `REFUSED-ALL-127` (s5, the harness never ran the
hooks), `REFUSED-TIMEOUT` (s11, a step was killed on its wall cap) and
`REFUSED-NORMALISE` (s12, the normalised bytes are not portable - see 5b).

REFUSED means the bytes do not survive. The freshly written `expect/` files are
removed and replaced by `expect/REFUSED-ALL-127`, so a caller who ignores
`record`'s non-zero exit cannot then verify green against a recording the
harness never really produced - `verify` reports "no recording" instead.

The whitelist is the FIRST COLUMN OF THE DEFECT TABLE in
`<family>/KNOWN-DEFECTS.md` (`| <case> | ... |`), not the whole file, so a
KNOWN-DEFECTS.md may describe the history of a fixed defect without re-arming
the guard for a case that is healthy again. Retiring the entry is part of
fixing the defect: `stop-gates/block-context-budget` and
`lib/override-audit-ack` kept their whitelist rows through the v1.6.0 env fix,
which left the s5 guard disarmed for the two cases it was written for.

<a id="wallcap"></a>
## 11. The wall cap is per invocation shape, and a 142 is never golden

Every run is wrapped in a `perl` alarm (macOS has no `timeout(1)`). The two
runners start different processes: a `legacy` step is ONE hook, while one
`sutra-turn run --event E` is that event's WHOLE pipeline (24 hooks for
`PreToolUse`). One flat cap is wrong by construction - a cold-cache
`--jobs 8` runner pass killed six `stop-gates` cases at 20s, and the truncated
ledgers surfaced as `no ledger row` FAILs that blamed parity for a harness
timeout.

| knob | default | caps |
|---|---|---|
| registration `timeout` | 8s when absent | one legacy step - its OWN budget (11a) |
| `SUTRA_STEP_TIMEOUT_SCALE` | 100 (integer percent, clamped >= 100) | lengthens that budget on BOTH legs |
| `SUTRA_CHARCAP_TIMEOUT` | 20s | OUTER cap on one legacy step, itself scaled |
| `SUTRA_CHARCAP_TURN_TIMEOUT` | 6x `SUTRA_CHARCAP_TIMEOUT` | one `sutra-turn run --event` invocation |

`verify --runner sutra-turn` reports exit 142 (SIGALRM) AS the wall cap - one
line naming the cap and the two knobs - instead of the diffs derived from a
half-written ledger. `record` REFUSES a case in which any step hit the cap and
discards it (`expect/REFUSED-TIMEOUT`, the s5 purge): a killed step records a
truncation, so freezing it would make every later `verify` depend on machine
load.

<a id="step-budget"></a>
### 11a. Both legs face the REGISTRATION'S OWN budget (v1.7.0)

One flat cap was also wrong against the runtime. `--runner sutra-turn` enforces
each registration's own `timeout_ms` (3000-15000 ms in `runtime/pipeline.json`,
scaled by `SUTRA_STEP_TIMEOUT_SCALE` in `runtime/shim.sh`), while the legacy leg
used to give every step the same 20s. A step that outlives its registered budget
therefore recorded exit `0` on the legacy leg - an expectation the runtime can
NEVER reach - so the resulting `124` diff was partly a harness artifact rather
than a parity defect.

Since v1.7.0 the legacy leg reads the registration's own timeout from
`hooks/hooks.json.step3` when that file is present (the full per-hook registry
`families.json` is derived from) and from `hooks/hooks.json` otherwise, in
seconds x1000, defaulting to 8000 ms when the registration carries none. It then
applies the SAME integer-percent `SUTRA_STEP_TIMEOUT_SCALE` clamp (>= 100, so the
knob can only ever lengthen a budget) that `runtime/shim.sh` applies, and rounds
UP to whole seconds because `perl`'s alarm has second granularity - the legacy
leg is never given LESS wall than the runtime got. `SUTRA_CHARCAP_TIMEOUT`
remains the OUTER cap, scaled by the same percent, so one pathological
registration (the 150s one) cannot hold the corpus for ten minutes.

Consequence for the corpus: a step that cannot finish inside its registered
budget is now REFUSED at record time on BOTH legs instead of being frozen as a
green the runtime can never reproduce, and a `124` under `--runner sutra-turn`
is a real recorded result. The shipped corpus was re-recorded with charcap
v1.7.2 by exactly this command, the gate's own scale setting:

```sh
SUTRA_CHARCAP_WORK=<private dir> SUTRA_CHARCAP_GOLDEN=<this dir> \
  SUTRA_STEP_TIMEOUT_SCALE=400 bin/sutra-charcap record --all --jobs 4
```

A replay at a LOWER scale faces shorter walls than the recording did.

---

Provenance: authored 2026-09-11 for `holding/plans/sutra-runtime/EXECUTION.md`
step 7. Family counts and the derivation rules were read from
`sutra/marketplace/plugin/hooks/hooks.json` (92 command entries, 7 events), not
from memory. Sections 1a, 3a, 8 and 9 were added 2026-09-12 with charcap v1.4.0
after a full-corpus replay from a second plugin tree reproduced 24 `ups`
`.fx` failures (`.enforcement/marker-resets.jsonl`) twice; the whole corpus was
re-recorded under the length-invariant roots afterwards. Sections 1b and 10,
and the s8 rewrite (per-case event dispatch, duplicate slots, the retired
post-deny note class), landed 2026-09-13 with charcap v1.6.0 after the recorder
was found using its own matcher rule (`permission/mcp-write` recorded zero steps
while the host runs `permission-gate.sh`) and its own env vector (two families
recorded all-127); the whole corpus was re-recorded under both fixes.
charcap v1.6.1 (2026-09-13) closed the two holes that fix left open - the
REFUSED recording was written to disk before the family aborted, and the two
KNOWN-DEFECTS entries for the env-split cases still whitelisted them - by
discarding a refused recording and by reading the whitelist from the defect
table's first column only; the whole corpus was re-recorded again. Section 11
and charcap v1.6.2 (2026-09-13) followed the first `--runner sutra-turn` pass
of that re-recorded corpus, in which six `stop-gates` cases were killed by the
20s cap and reported as parity diffs. Section 11a and charcap v1.7.0
(2026-09-15) closed the other half of that hole, found by the round-6 review:
the legacy leg capped every step at the flat `SUTRA_CHARCAP_TIMEOUT` and never
applied the registration's own 3000-15000 ms budget, so an expectation of exit
`0` could be out of the runtime's reach and a `124` diff was partly a harness
artifact. All 9 families were re-recorded with v1.7.0 at
`SUTRA_STEP_TIMEOUT_SCALE=400 --jobs 4` and replayed with
`verify --all --runner legacy --jobs 4` at the same scale.

charcap v1.7.1 and v1.7.2 (2026-09-16) closed the normalisation holes the
round-7 review found, and the corpus shipped here is THEIR recording, not
v1.7.0's. Four normaliser changes, all of them s5b contract: the `<VERSION>`
rule was added so a release bump cannot break the corpus; its LEFT guard was
then narrowed to `[^0-9A-Za-z._/]`, which makes a HYPHEN a guard, so
`sutra-core-2.278.0` normalises while `a.1.2.3` and `core/2.274.2/` stay raw;
its TRAILING guard was widened to accept a dot followed by a non-digit or end
of line, so `plugin v2.278.0.` normalises while `1.2.3.4` and `10.0.0.1:8080`
stay raw; a DOTTED DATE rule (`2026.09.16` -> `<TS>`) was emitted BEFORE the
version rule, because both shapes are `digits.digits.digits` and a dotted date
is a date in every hook that prints one; and the `<USER>` / `<HOST>` identity
rules were made WORD-BOUND on both sides (and emitted twice, like the version
rule, since each consumes its trailing guard) after the unguarded form froze
`sankalp<USER>/sutra-data` and failed 22 `session` checks on every box whose
`id -un` differs - a CI runner's is `runner`. The `record` REFUSAL class s12
backs those rules: a recording whose `expect/` bytes still carry a
`<USER>`/`<HOST>` token glued to a word character, or a raw `x.y.z` the version
rule should have taken, is discarded (`expect/REFUSED-NORMALISE`) instead of
being frozen - the assertion, not the regex, is what keeps the next release bump
green. Two more changes landed with them: `derive-families` now prefers
`hooks/hooks.json.step3` (the full per-hook registry) over the collapsed runtime
`hooks/hooks.json` and REFUSES a registry that names no `hooks/` script at all
(s14), and `families.json` gained `recorded_on` (the recording box's
`uname -s`), which `runtime/tests/test-charcap-parity.sh` reads to skip a
cross-platform replay (s5b). Re-recorded 2026-09-16 with
`SUTRA_STEP_TIMEOUT_SCALE=400 record --all --jobs 4` (`generated_by`:
`sutra-charcap 1.7.2 derive-families`; log `record-all-v172.log`): 9 families,
259 cases, 1 NO-MATCH.
