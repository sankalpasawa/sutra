#!/bin/bash
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/spec-check.sh
# WHY_NOT_L0_KIND=n/a
# WHY_NOT_L0_REASON=n/a
# TS=2026-09-12
#
# spec-check.sh — static validator for runtime/pipeline.json (Sutra Runtime W0a, step 5).
#
# Usage:  bash runtime/spec-check.sh [<spec.json>] [<hooks.json>]
#   <spec.json>   default: <dir of this script>/pipeline.json
#   <hooks.json>  default: <dir of this script>/../hooks/hooks.json.step3 when
#                 that file exists, else ../hooks/hooks.json
#                 (resolved from THIS script, never from the spec, so a red
#                  fixture under runtime/tests/ is checked against the same
#                  registry as the real spec)
#
#                 WHY .step3 FIRST. hooks.json is collapsed once the runtime
#                 lands - one sutra-turn entry per event the pipeline declares
#                 with at least one step, plus the bare canary (7 registrations
#                 today). Checking the spec against THAT would assert nothing:
#                 the registry the steps were derived from is the snapshot
#                 hooks.json.step3, and that is the file completeness and order
#                 must be judged against. Every count below is derived with jq
#                 from the files themselves; no registration count is written
#                 into this script, because a literal goes stale the next time
#                 a hook is registered.
#
# Exit codes:  0 = spec valid   3 = spec invalid (every failure is printed)
#
# Checks:
#   1  spec_version is a string, contract_version is a number
#   2  events carries the 6 canonical event keys the runtime serves today, plus
#      UserPromptExpansion and SubagentStop optionally (SubagentStop lands at
#      EXECUTION step 37; UserPromptExpansion is declarable again the day a step
#      exists for it - see check 13); no other key
#   3  every step has: unique id, matcher, class in A|B|C, impl, timeout_ms > 0,
#      replaces[] (an array; non-empty for a shim: impl — native: and det: may
#      carry [], since neither replaces a hooks.json registration; check 14 is
#      what still requires [] exactly on a native: step), killswitch_aliases[],
#      on_error in warn|block_passthrough
#   4  no step declares an llm_slot / llm_slots on a deterministic impl
#      (impl prefix shim: / native: / det:)
#   5  context + wall-clock budgets present; per-event sum(timeout_ms) within budget
#   6  the 3 profiles exist
#   7  deleted[] entries each carry a script and a non-empty reason
#   8  completeness against hooks.json: every registration (event, matcher,
#      script) is covered by EXACTLY ONE step, every registered script is
#      accounted for by a step's replaces[] or by deleted[], and no step
#      replaces a script that is not registered
#   9  ORDER: for every declared event, the ordered impl basenames of events[E] equal the
#      ordered command basenames of the registry's E, order-preserving-unique so
#      a script registered twice in one event compares once. Parity depends on
#      this and nothing else asserted it; registrations that ARE the runtime
#      (any token whose basename is sutra-turn or sutra-canary) are skipped.
#  10  REGISTRY SYNC: the live hooks/hooks.json and its snapshot
#      hooks/hooks.json.step3 must not drift apart.
#        collapsed (any command basename is sutra-turn or sutra-canary):
#            it must hold EXACTLY one runtime registration per event the
#            pipeline declares plus one canary (7 today, 8 with SubagentStop) - one
#            `sutra-turn run --event <E>` per declared event and one bare
#            sutra-canary at UserPromptSubmit - and nothing else.
#        not collapsed:
#            it must equal hooks.json.step3 command for command, in order.
#      WHY. Checks 8 and 9 deliberately read .step3. Without this check a 9th
#      registration added the old way to hooks.json is invisible to spec-check,
#      invisible to validate-hook-paths (which reads the collapsed file) and
#      invisible to the release gate: it would run on the fleet while no spec
#      step, no ledger row and no parity case knew about it.
#  11  matcher_semantics is present and equals "anchored-ere" - the matcher rule
#      the runtime implements (omitted or * = all; a plain name list split on |
#      = exact; anything else = an anchored extended regular expression) is
#      declared IN the spec, so a reader of pipeline.json does not have to
#      reverse it out of sutra-turn's source.
#  12  HOST CAP vs STEP BUDGETS: for every event the pipeline declares, the
#      timeout on that event's `sutra-turn run --event <E>` registration in the
#      LIVE collapsed hooks.json, in milliseconds, must be >= the largest
#      timeout_ms of the steps folded under it, and budgets.event_wall_ms[E]
#      must be >= that same largest step budget. Exit 3 names the event.
#      WHY. Before the collapse each slow hook carried its own host timeout, so
#      a hook that overran was the only thing killed. Under one registration
#      per event the host cap applies to sutra-turn itself: a 15 s step under
#      an 8 s cap means the host SIGKILLs the runtime mid-step and the ENTIRE
#      event is lost — no step rows, no emit, no stage_digest, only the
#      orphan_turn row a later turn writes. That is a fleet-wide regression
#      that no other check here can see, because the spec and the registry are
#      each internally consistent. Both sides are DERIVED from the two files;
#      nothing about a cap is written into this script.
#      NOTE. The LARGEST step, not the sum, is what the cap must cover — with
#      one exception (D4, W1-FAST-PATH MVP-1): a "phase":"post" step is never
#      spawned in pass 1: pass 2's serial pass runs every post step ONE AT A
#      TIME, after every parallel (non-post) step of the event has already
#      finished. So the event's real wall is max(timeout_ms of its non-post
#      steps) + sum(timeout_ms of its post steps), and $need below is exactly
#      that. An event with no post step keeps the plain max(step) it always
#      had. event_wall_ms may therefore sit ABOVE the host cap — it is the
#      aggregate ceiling check 5 measures the per-event timeout SUM against, a
#      different quantity from the per-step cap here.
#  13  NO DEAD EVENT: an event the pipeline declares with ZERO steps must not be
#      registered in the live collapsed hooks.json, and every
#      `sutra-turn run --event <E>` registration in it must name an event the
#      pipeline declares with at least one step. Exit 3 naming the event.
#      WHY. UserPromptExpansion shipped registered here while the pipeline
#      declared it as an empty array and hooks.json.step3 carried no such
#      registration at all — the fleet fires nothing on that path today. After
#      the collapse every prompt expansion would have forked sutra-turn, read
#      the registry, selected no step, written an orphan_turn + stage_digest row
#      and exited: pure overhead plus a new failure surface on a path that has
#      none. Checks 8-10 cannot see it (the pipeline and the registry are each
#      internally consistent, and .step3 has nothing to compare against for an
#      event it never registered), so the binding is asserted here in both
#      directions. Declaring the event again is legitimate the day it has a
#      step; declaring it EMPTY, or registering it unbacked, is not.
#  14  NATIVE STEP SCRIPTS EXIST (D18, W1-FAST-PATH MVP-1): for every step whose
#      impl is native:<n>, <dir of this script>/steps/<n>.sh must exist and be
#      executable, its phase must be exactly "post" (an absent phase would let
#      pass 1 spawn it in parallel with the marker reset — D4's serial post
#      pass is the only caller a native step may have; codex P2 2026-09-16),
#      and its replaces[] must be exactly [] (check 3's
#      shim: exemption on replaces[] is not a licence for a native step to
#      claim a hooks.json registration). Checks 8-10 never see a native step —
#      it appears in no hooks.json entry — so its only assertable fact is a
#      FILESYSTEM one, checked here directly rather than derived from the two
#      registries.
#
# Dependencies: bash 3.2 (macOS system bash) + jq. No GNU coreutils, no python.

set -u

_SELF_DIR=$(cd "$(dirname "$0")" && pwd)
SPEC="${1:-$_SELF_DIR/pipeline.json}"
LIVE_HOOKS="$_SELF_DIR/../hooks/hooks.json"
STEP3="$_SELF_DIR/../hooks/hooks.json.step3"
if [ -f "$STEP3" ]; then
  _DEFAULT_HOOKS="$STEP3"
else
  _DEFAULT_HOOKS="$LIVE_HOOKS"
fi
HOOKS="${2:-${SUTRA_HOOKS_JSON:-$_DEFAULT_HOOKS}}"

fail() { printf 'spec-check: FAIL — %s\n' "$1" >&2; exit 3; }

command -v jq >/dev/null 2>&1 || fail "jq not on PATH"
[ -r "$SPEC" ]  || fail "spec not readable: $SPEC"
[ -r "$HOOKS" ] || fail "hooks.json not readable: $HOOKS (pass it as argument 2 or set SUTRA_HOOKS_JSON)"
jq -e . "$SPEC"  >/dev/null 2>&1 || fail "spec is not valid JSON: $SPEC"
jq -e . "$HOOKS" >/dev/null 2>&1 || fail "hooks.json is not valid JSON: $HOOKS"

ERRS=$(jq -r -n --slurpfile S "$SPEC" --slurpfile H "$HOOKS" '
  def base: sub(".*/"; "");
  def isdet: (type == "string") and (startswith("shim:") or startswith("native:") or startswith("det:"));

  ($S[0]) as $s
  | ($H[0]) as $h
  # $EVALL: every event a pipeline MAY declare, in canonical host order.
  # $EVOPT: the ones it MAY omit - SubagentStop lands at EXECUTION step 37, and
  #         UserPromptExpansion is omitted today because the fleet registers no
  #         hook on that path (see check 13; declaring it again is legitimate
  #         the day it carries a step).
  # $EVREQ: the rest - what every pipeline must declare. Derived by subtraction
  #         so the canonical order lives in ONE list.
  # $EV is what THIS spec actually declares, in canonical order - every count
  # below is derived from it, never written down, so adding an event does not
  # turn this script red.
  | ["SessionStart","UserPromptExpansion","UserPromptSubmit","PreToolUse","PostToolUse","PermissionRequest","Stop","SubagentStop"] as $EVALL
  | ["UserPromptExpansion","SubagentStop"] as $EVOPT
  | ($EVALL - $EVOPT) as $EVREQ
  | (($s.events // {}) | keys) as $EVDECL
  | ([ $EVALL[] as $e1 | select(($EVDECL | index($e1)) != null) | $e1 ]) as $EV
  | ([ $h.hooks | to_entries[] | .key as $e | .value[] | ((.matcher // "*")) as $m
       | (.hooks // [])[]
       | {event:$e, matcher:$m, script:(.command | split(" ") | last | base)} ]) as $regs
  | ([ $EV[] as $e | (($s.events // {})[$e] // [])[] | . + {event:$e} ]) as $steps
  | ([ $steps[] | (.replaces // [])[] | base ] | unique) as $repl
  | ([ ($s.deleted // [])[] | (.script // "") | base ] | unique) as $del
  | ([ $regs[].script ] | unique) as $regscripts
  | [
      (if ($s.spec_version | type) != "string"
         then "spec_version missing or not a string" else empty end),
      (if ($s.contract_version | type) != "number"
         then "contract_version missing or not a number" else empty end),
      (if (($s.matcher_semantics // "") != "anchored-ere")
         then "matcher_semantics must be present and equal \"anchored-ere\" (got \($s.matcher_semantics // "<absent>")) — the matcher rule the runtime implements is declared in the spec, not only in sutra-turn"
         else empty end),
      (if (($EVREQ - $EVDECL) | length) > 0
         then "events is missing canonical key(s) [\(($EVREQ - $EVDECL) | join(", "))]; got [\($EVDECL | join(", "))]"
         else empty end),
      (if (($EVDECL - $EVALL) | length) > 0
         then "events carries non-canonical key(s) [\(($EVDECL - $EVALL) | join(", "))]; allowed keys are [\($EVALL | join(", "))]"
         else empty end),

      ($steps[] | select((.id | type) != "string" or ((.id // "") | length) == 0)
        | "a step in \(.event) has no id"),
      ($steps[] | select(.class != "A" and .class != "B" and .class != "C")
        | "step \(.id // "<no id>") has class \(.class // "<none>"), expected A, B or C"),
      ($steps[] | select((.timeout_ms | type) != "number" or (.timeout_ms <= 0))
        | "step \(.id // "<no id>") has no positive timeout_ms"),
      ($steps[] | select((.impl | type) != "string" or ((.impl // "") | length) == 0)
        | "step \(.id // "<no id>") has no impl"),
      ($steps[] | select((.matcher | type) != "string")
        | "step \(.id // "<no id>") has no matcher"),
      ($steps[] | select(.on_error != "warn" and .on_error != "block_passthrough")
        | "step \(.id // "<no id>") has on_error \(.on_error // "<none>"), expected warn or block_passthrough"),
      ($steps[] | select(((.replaces // null) | type) != "array")
        | "step \(.id // "<no id>") has no replaces[] (must be an array; [] is allowed for a native: or det: step, see check 14)"),
      ($steps[] | select(((.impl // "") | startswith("shim:")) and ((.replaces // []) | length) == 0)
        | "step \(.id // "<no id>") has an empty replaces[] (a shim: step must replace at least one legacy script)"),
      ($steps[] | select(((.killswitch_aliases // null) | type) != "array")
        | "step \(.id // "<no id>") has no killswitch_aliases[]"),
      ($steps[] | select((.impl | isdet) and ((.llm_slot // .llm_slots // false) != false))
        | "step \(.id) declares an llm_slot on a deterministic impl (\(.impl))"),
      ([ $steps[].id ] | group_by(.) | map(select(length > 1))[]
        | "duplicate step id \(.[0])"),

      (if (($s.budgets // null) | type) != "object" then "budgets missing" else empty end),
      (if (($s.budgets.context.render_chars_max // null) | type) != "number"
         then "budgets.context.render_chars_max missing" else empty end),
      ($EV[] as $e
        | (($s.budgets.event_wall_ms // {})[$e]) as $cap
        | if ($cap | type) != "number"
            then "budgets.event_wall_ms.\($e) missing"
            else ([ $steps[] | select(.event == $e) | .timeout_ms ] | add // 0) as $sum
                 | if $sum > $cap
                     then "event \($e): step timeout_ms sum \($sum) exceeds budget \($cap)"
                     else empty end
          end),

      (["individual","project","company"][] as $p
        | if (($s.profiles // {})[$p] | type) != "object"
            then "profiles.\($p) missing" else empty end),

      (if (($s.deleted // null) | type) != "array" or (($s.deleted // []) | length) == 0
         then "deleted[] missing or empty" else empty end),
      (($s.deleted // [])[]
        | select(((.script // "") | length) == 0 or ((.reason // "") | length) == 0)
        | "deleted entry \(.script // "<no script>") has no script or no reason"),

      ($regs[] as $r
        | ([ $steps[]
             | select(.event == $r.event)
             | select((.matcher // "*") == $r.matcher)
             | select(((.replaces // []) | map(base) | index($r.script)) != null) ] | length) as $n
        | if $n == 1 then empty
          elif $n == 0 then "registration \($r.event) / \($r.matcher) / \($r.script) has no step"
          else "registration \($r.event) / \($r.matcher) / \($r.script) is covered by \($n) steps" end),

      ($regscripts[] as $sc
        | if (($repl | index($sc)) != null) or (($del | index($sc)) != null) then empty
          else "registered script \($sc) appears in no replaces[] and in no deleted[] entry" end),

      ($repl[] as $sc
        | if ($regscripts | index($sc)) != null then empty
          else "step replaces \($sc), which is not registered in hooks.json" end)
    ]
  | .[]
') || fail "jq evaluation failed on $SPEC"

if [ -n "$ERRS" ]; then
  printf '%s\n' "$ERRS" >&2
  printf 'spec-check: FAIL — %s error(s) in %s\n' "$(printf '%s\n' "$ERRS" | wc -l | tr -d ' ')" "$SPEC" >&2
  exit 3
fi

# ---- check 9: per-event order invariant ------------------------------------
# Parity is an ORDERED property: sutra-turn runs events[E] top to bottom, and
# charcap compares that against the legacy host running the registry top to
# bottom. A spec that is complete but reordered passes every check above and
# fails parity, so the order is asserted here, per event, by name.
ORDER_ERRS=$(jq -r -n --slurpfile S "$SPEC" --slurpfile H "$HOOKS" --arg hf "$HOOKS" '
  def base: sub(".*/"; "");
  # order-preserving unique: a script registered twice inside one event is one
  # entry on both sides, in the position of its FIRST appearance.
  def opu: reduce .[] as $x ([]; if (index($x)) == null then . + [$x] else . end);

  ($S[0]) as $s
  | ($H[0]) as $h
  | (["SessionStart","UserPromptExpansion","UserPromptSubmit","PreToolUse","PostToolUse","PermissionRequest","Stop","SubagentStop"]) as $EVALL
  | (($s.events // {}) | keys) as $EVDECL
  | ([ $EVALL[] as $e1 | select(($EVDECL | index($e1)) != null) | $e1 ]) as $EV
  | $EV[] as $e
  | ([ (($s.events // {})[$e] // [])[]
       | (.impl // "")
       | select(startswith("shim:"))
       | sub("^shim:"; "")
       | base ] | opu) as $specorder
  | ([ (($h.hooks // {})[$e] // [])[]
       | (.hooks // [])[]
       | select((.type // "command") == "command")
       | (.command | split(" ") | map(base)) as $toks
       | select((($toks | index("sutra-turn")) == null)
                and (($toks | index("sutra-canary")) == null))
       | ($toks | last) ] | opu) as $regorder
  | if $specorder == $regorder then empty
    else "event \($e): step order does not match registration order in \($hf)\n    spec: \($specorder | join(" "))\n    regs: \($regorder | join(" "))"
    end
') || fail "jq evaluation failed on the order check for $SPEC"

if [ -n "$ORDER_ERRS" ]; then
  printf '%s\n' "$ORDER_ERRS" >&2
  printf 'spec-check: FAIL — event step order differs from %s\n' "$HOOKS" >&2
  exit 3
fi

# ---- check 10: live registry vs its snapshot -------------------------------
# The live hooks/hooks.json is read here NO MATTER which registry argument 2
# selected: checks 8 and 9 judge the spec against .step3, so without this the
# collapsed file nobody diffs could grow a 10th entry unseen.
SYNC_ERRS=""
if [ ! -r "$LIVE_HOOKS" ]; then
  SYNC_ERRS="live registry not readable: $LIVE_HOOKS"
else
  jq -e . "$LIVE_HOOKS" >/dev/null 2>&1 || fail "live hooks.json is not valid JSON: $LIVE_HOOKS"
  COLLAPSED=$(jq -r '
    [ .hooks // {} | to_entries[] | .value[] | (.hooks // [])[]
      | (.command // "") | split(" ")[] | sub(".*/"; "") ]
    | if (index("sutra-turn") != null or index("sutra-canary") != null)
      then "yes" else "no" end' "$LIVE_HOOKS")

  if [ "$COLLAPSED" = "yes" ]; then
    SYNC_ERRS=$(jq -r -n --slurpfile L "$LIVE_HOOKS" --slurpfile S "$SPEC" '
      def base: sub(".*/"; "");
      ($L[0]) as $h
      | ($S[0]) as $s
      # DERIVED, never written down. The expected number of collapsed
      # registrations is "one sutra-turn per canonical event THIS pipeline
      # declares, plus exactly one sutra-canary" - 7 today, 8 the day
      # SubagentStop joins the spec (EXECUTION step 37). A literal here went
      # red on a change the design calls for; the per-event uniqueness asserts
      # below are what actually do the work.
      | (["SessionStart","UserPromptExpansion","UserPromptSubmit","PreToolUse","PostToolUse","PermissionRequest","Stop","SubagentStop"]) as $EVALL
      | (($s.events // {}) | keys) as $EVDECL
      | ([ $EVALL[] as $e1 | select(($EVDECL | index($e1)) != null) | $e1 ]) as $EV
      | (($EV | length) + 1) as $EXPECTED
      | ([ $h.hooks // {} | to_entries[] | .key as $e | .value[]
           | ((.matcher // "*")) as $m | (.hooks // [])[]
           | {event:$e, matcher:$m, cmd:(.command // ""),
              toks:((.command // "") | split(" ") | map(base))} ]) as $regs
      | [
          ($regs[] | select((.toks | index("sutra-turn")) == null
                            and (.toks | index("sutra-canary")) == null)
            | "collapsed hooks.json still registers a legacy hook: \(.event) / \(.matcher) / \(.cmd)"),
          (if ($regs | length) != $EXPECTED
             then "collapsed hooks.json holds \($regs | length) registrations, expected exactly \($EXPECTED) (one sutra-turn per event the pipeline declares [\($EV | join(", "))] + one sutra-canary)"
             else empty end),
          ($EV[] as $e
            | ([ $regs[] | select(.event == $e)
                 | select((.toks | index("sutra-turn")) != null)
                 | select((.cmd | test("--event[[:space:]]+" + $e + "([[:space:]]|$)"))) ] | length) as $n
            | if $n == 1 then empty
              else "collapsed hooks.json has \($n) `sutra-turn run --event \($e)` registrations under \($e), expected exactly 1"
              end),
          (([ $regs[] | select((.toks | index("sutra-canary")) != null) ] | length) as $c
            | if $c != 1
                then "collapsed hooks.json has \($c) sutra-canary registrations, expected exactly 1"
                else empty end),
          ($regs[] | select((.toks | index("sutra-canary")) != null)
            | select(.event != "UserPromptSubmit")
            | "sutra-canary is registered under \(.event), expected UserPromptSubmit")
        ] | .[]') || fail "jq evaluation failed on the registry-sync check"
  else
    if [ ! -r "$STEP3" ]; then
      SYNC_ERRS="hooks.json is not collapsed and there is no snapshot to compare it with: $STEP3"
    else
      jq -e . "$STEP3" >/dev/null 2>&1 || fail "hooks.json.step3 is not valid JSON: $STEP3"
      SYNC_ERRS=$(jq -r -n --slurpfile L "$LIVE_HOOKS" --slurpfile T "$STEP3" '
        def rows: [ (.hooks // {}) | to_entries[] | .key as $e | .value[]
                    | ((.matcher // "*")) as $m | (.hooks // [])[]
                    | "\($e)\t\($m)\t\(.command // "")" ];
        (($L[0]) | rows) as $live
        | (($T[0]) | rows) as $snap
        | [ (if ($live | length) != ($snap | length)
               then "hooks.json holds \($live | length) registrations, hooks.json.step3 holds \($snap | length)"
               else empty end),
            (range(0; ([($live | length), ($snap | length)] | min)) as $i
              | if ($live[$i]) == ($snap[$i]) then empty
                else "registration #\($i + 1) differs — hooks.json: \($live[$i] | gsub("\t"; " / ")) ; hooks.json.step3: \($snap[$i] | gsub("\t"; " / "))"
                end),
            (if ($live | length) > ($snap | length)
               then ($live[($snap | length):][] | "hooks.json has an extra registration not in hooks.json.step3: \(. | gsub("\t"; " / "))")
               else ($snap[($live | length):][] | "hooks.json.step3 has a registration missing from hooks.json: \(. | gsub("\t"; " / "))")
               end)
          ] | .[]') || fail "jq evaluation failed on the registry-sync check"
    fi
  fi
fi

if [ -n "$SYNC_ERRS" ]; then
  printf '%s\n' "$SYNC_ERRS" >&2
  printf 'spec-check: FAIL — %s and %s are out of sync\n' "$LIVE_HOOKS" "$STEP3" >&2
  exit 3
fi

# ---- check 12: host cap vs step budgets ------------------------------------
# Only meaningful once hooks.json is collapsed: before that every legacy hook
# still carries its own host timeout and there is no runtime registration whose
# cap could be too small. Reads the LIVE registry for the same reason check 10
# does — argument 2 points at .step3, and .step3 is the PRE-collapse snapshot.
CAP_ERRS=""
if [ "${COLLAPSED:-no}" = "yes" ]; then
  CAP_ERRS=$(jq -r -n --slurpfile L "$LIVE_HOOKS" --slurpfile S "$SPEC" '
    def base: sub(".*/"; "");
    ($L[0]) as $h
    | ($S[0]) as $s
    | (["SessionStart","UserPromptExpansion","UserPromptSubmit","PreToolUse","PostToolUse","PermissionRequest","Stop","SubagentStop"]) as $EVALL
    | (($s.events // {}) | keys) as $EVDECL
    | ([ $EVALL[] as $e1 | select(($EVDECL | index($e1)) != null) | $e1 ]) as $EV
    | (($s.budgets.step_default_ms // 0)) as $DEF
    | $EV[] as $e
    | ((($s.events // {})[$e]) // []) as $st
    # NEED (D4/D18): pass 1 spawns every non-post step of the event in
    # PARALLEL (max); pass 2 then runs every "phase":"post" step SERIALLY, one
    # at a time, after the single wait call (sum). The real wall of the event
    # is max(non-post) + sum(post) — an event with no post step keeps the
    # plain max(step) it always had, because sum(post) is then 0. An event
    # that declares no step at all still inherits step_default_ms the day a
    # step is added, so that is its floor — the cap must already cover it.
    | ([ $st[] | select((.phase // "") != "post") | (.timeout_ms // 0) ] | max // 0) as $maxnonpost
    | ([ $st[] | select((.phase // "") == "post") | (.timeout_ms // 0) ] | add // 0) as $sumpost
    | ($maxnonpost + $sumpost) as $rawneed
    | (if ($st | length) == 0 then $DEF else $rawneed end) as $need
    | ([ $st[] | select((.phase // "") != "post") | select((.timeout_ms // 0) == $maxnonpost) | (.id // "<no id>") ] | .[0] // "<none>") as $slowest
    | ([ ((($h.hooks // {})[$e]) // [])[]
         | (.hooks // [])[]
         | select((.type // "command") == "command")
         | select(((.command // "") | split(" ") | map(base) | index("sutra-turn")) != null)
         | select((.command // "") | test("--event[[:space:]]+" + $e + "([[:space:]]|$)"))
         | .timeout ]) as $caps
    | (($s.budgets.event_wall_ms // {})[$e]) as $wall
    | ((($need + 999) / 1000 | floor) + 5) as $want
    | ("max non-post \($maxnonpost)ms (step \($slowest)) + post total \($sumpost)ms") as $breakdown
    | [
        (if ($caps | length) == 0
           then "event \($e): the collapsed hooks.json has no `sutra-turn run --event \($e)` registration to carry a host timeout"
         elif (($caps[0] | type) != "number")
           then "event \($e): the sutra-turn registration carries no numeric timeout — the host cap must be declared explicitly, not inherited from the host default"
         elif (($caps[0] * 1000) < $need)
           then "event \($e): hooks.json timeout \($caps[0])s (\($caps[0] * 1000)ms) is BELOW the largest step budget \($need)ms (\($breakdown)) — the host would SIGKILL sutra-turn mid-step and lose the whole event; register at least \($want)s"
         else empty end),
        (if ($wall | type) != "number"
           then "event \($e): budgets.event_wall_ms.\($e) missing"
         elif ($wall < $need)
           then "event \($e): budgets.event_wall_ms \($wall)ms is BELOW the largest step budget \($need)ms (\($breakdown))"
         else empty end)
      ] | .[]') || fail "jq evaluation failed on the host-cap check"
fi

if [ -n "$CAP_ERRS" ]; then
  printf '%s\n' "$CAP_ERRS" >&2
  printf 'spec-check: FAIL — host timeouts in %s do not cover the step budgets in %s\n' "$LIVE_HOOKS" "$SPEC" >&2
  exit 3
fi

# ---- check 13: no dead event -----------------------------------------------
# Runs AFTER check 12 on purpose: an event with zero steps still has a host cap
# and an event_wall_ms to answer for, and check 12's message names the budget
# that is wrong. This check is about the event existing at all.
# Both arms read the LIVE registry (the collapsed file is where a dead
# registration actually costs a fork), and both are derived from the two files.
DEAD_ERRS=""
if [ "${COLLAPSED:-no}" = "yes" ]; then
  DEAD_ERRS=$(jq -r -n --slurpfile L "$LIVE_HOOKS" --slurpfile S "$SPEC" '
    def base: sub(".*/"; "");
    ($L[0]) as $h
    | ($S[0]) as $s
    | (["SessionStart","UserPromptExpansion","UserPromptSubmit","PreToolUse","PostToolUse","PermissionRequest","Stop","SubagentStop"]) as $EVALL
    | (($s.events // {}) | keys) as $EVDECL
    | ([ $EVALL[] as $e1 | select(($EVDECL | index($e1)) != null) | $e1 ]) as $EV
    # events the pipeline declares with at least one step
    | ([ $EV[] | select(((($s.events // {})[.]) // []) | length > 0) ]) as $EVLIVE
    # events the collapsed registry forks sutra-turn for
    | ([ ($h.hooks // {}) | to_entries[] | .key as $e | .value[] | (.hooks // [])[]
         | select((.type // "command") == "command")
         | select((((.command // "") | split(" ") | map(base) | index("sutra-turn"))) != null)
         | $e ] | unique) as $EVREG
    | [
        # NOTE: every membership test binds the event to $e first. `index(.)`
        # after a pipe would test the ARRAY against itself - the pipe rebinds
        # `.` to the left-hand side - and silently find everything.
        ($EV[] | . as $e
          | select(($EVLIVE | index($e)) == null)
          | if ($EVREG | index($e)) != null
              then "event \($e): declared in the pipeline with ZERO steps and still registered in the collapsed hooks.json — every \($e) would fork sutra-turn, select no step and write only an orphan_turn + stage_digest row; drop the event from events[] and from its hooks.json registration, or give it a step"
              else "event \($e): declared in the pipeline with ZERO steps — an empty event declaration is not a spec, it is a placeholder; drop it from events[] (and from budgets.event_wall_ms) until a step exists for it"
            end),
        ($EVREG[] | . as $e
          | select(($EVLIVE | index($e)) == null)
          | select(($EV | index($e)) == null)
          | "event \($e): the collapsed hooks.json registers `sutra-turn run --event \($e)` but the pipeline does not declare it — the runtime would fork, find no steps and exit; drop the registration or declare the event with at least one step")
      ] | .[]') || fail "jq evaluation failed on the dead-event check"
fi

if [ -n "$DEAD_ERRS" ]; then
  printf '%s\n' "$DEAD_ERRS" >&2
  printf 'spec-check: FAIL — %s declares or %s registers an event with no steps\n' "$SPEC" "$LIVE_HOOKS" >&2
  exit 3
fi

# ---- check 14: native step scripts exist -----------------------------------
# A native:<n> impl is not a registration replay - checks 8-10 never see it,
# because it appears in no hooks.json entry. Its only assertable fact is a
# FILESYSTEM one: does <dir of this script>/steps/<n>.sh exist and carry the
# exec bit, does it keep phase absent-or-"post" (pass 1 never spawns it - D4's
# serial post pass after `wait` is the only caller), and does it still carry
# replaces: [] exactly (check 3's shim: exemption is not a licence for a
# native step to claim a hooks.json registration a shim step would otherwise
# own). One row per native: step, read with jq, judged in bash because
# existence and the exec bit are filesystem facts, not JSON facts.
NATIVE_ROWS=$(jq -r '
  [ (.events // {}) | to_entries[] | .key as $e | .value[]
    | select((.impl // "") | startswith("native:"))
    | { event: $e, id: (.id // "<no id>"),
        n: ((.impl) | sub("^native:"; "")),
        phase: (.phase // ""),
        replaces: (.replaces // null) } ]
  | .[]
  | [ .event, .id, .n, .phase, (.replaces | tojson) ] | @tsv
' "$SPEC" 2>/dev/null) || fail "jq evaluation failed on the native-step check"

NATIVE_ERRS=""
if [ -n "$NATIVE_ROWS" ]; then
  while IFS='	' read -r N_EVENT N_ID N_NUM N_PHASE N_REPL; do
    [ -n "${N_ID:-}" ] || continue
    N_SCRIPT="$_SELF_DIR/steps/$N_NUM.sh"
    if [ ! -f "$N_SCRIPT" ]; then
      NATIVE_ERRS="${NATIVE_ERRS}event $N_EVENT: step $N_ID (native:$N_NUM) has no script at $N_SCRIPT
"
    elif [ ! -x "$N_SCRIPT" ]; then
      NATIVE_ERRS="${NATIVE_ERRS}event $N_EVENT: step $N_ID (native:$N_NUM) script $N_SCRIPT is not executable
"
    fi
    case "$N_PHASE" in
      post) ;;
      *)
        NATIVE_ERRS="${NATIVE_ERRS}event $N_EVENT: step $N_ID (native:$N_NUM) has phase \"$N_PHASE\", expected \"post\" (a native step runs only in the serial post pass; an absent phase would spawn it in pass 1 and race the marker reset)
" ;;
    esac
    if [ "$N_REPL" != "[]" ]; then
      NATIVE_ERRS="${NATIVE_ERRS}event $N_EVENT: step $N_ID (native:$N_NUM) has replaces $N_REPL, expected exactly []
"
    fi
  done <<NATIVE_EOF
$NATIVE_ROWS
NATIVE_EOF
fi

if [ -n "$NATIVE_ERRS" ]; then
  printf '%s' "$NATIVE_ERRS" >&2
  printf 'spec-check: FAIL — a native: step in %s fails check 14\n' "$SPEC" >&2
  exit 3
fi

STEPS=$(jq '[.events[][]] | length' "$SPEC")
DEL=$(jq '.deleted | length' "$SPEC")
REGS=$(jq '[.hooks[][].hooks[]] | length' "$HOOKS")
LIVEREGS=$(jq '[.hooks[][].hooks[]] | length' "$LIVE_HOOKS" 2>/dev/null || echo '?')
printf 'spec-check: OK — %s steps cover %s registrations; %s deleted entries; live registry %s entries (%s)\n' \
  "$STEPS" "$REGS" "$DEL" "$LIVEREGS" "$SPEC"
exit 0
