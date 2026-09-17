#!/usr/bin/env bash
# steps.sh - the step ledger shared by the three adherence native steps and
# bin/sutra-steps (Sutra Runtime, adherence row 1). bash 3.2: no associative
# arrays, no mapfile, no ${var,,}.
#
# One ledger per turn at .sutra/turn/<sid>/<turn>.steps.json:
#   { turn_id, session_id, mode, opened_ts, unit,
#     steps:[{n,id,producer,status,detail}], mutations:[...], closed:null|{...} }
#
# Statuses: done | pending | gated | open | missing
#
# LAYER=L0
# SCOPE=fleet
# TARGET_PATH=sutra/marketplace/plugin/runtime/lib/steps.sh

sutra_steps_path() {  # <proj> <sid> <turn>
  printf '%s/.sutra/turn/%s/%s.steps.json' "$1" "$2" "$3"
}
sutra_artifact_path() {  # <proj> <sid> <turn> <kind>
  printf '%s/.sutra/turn/%s/%s.%s.json' "$1" "$2" "$3" "$4"
}
sutra_artifact_rel() {  # <sid> <turn> <kind> -> project-relative path
  printf '.sutra/turn/%s/%s.%s.json' "$1" "$2" "$3"
}

# sutra_steps_write <path> <json>: atomic replace.
sutra_steps_write() {
  _sw_tmp="$1.tmp.$$"
  if printf '%s\n' "$2" > "$_sw_tmp" 2>/dev/null; then
    mv -f "$_sw_tmp" "$1" 2>/dev/null
  fi
}

# sutra_steps_bash_mutation <command> -> 0 when the command mutates, 1 when
# it is read-only. The three regexes are hooks/atom-floor.sh's, verbatim
# (2026-09-16), so the two gates never disagree about what a mutation is.
sutra_steps_bash_mutation() {
  # Quote/comment strip, then atom-floor.sh:95's noise pass (N>/dev/null, &>/dev/null,
  # N>&M) so a diagnostic redirect is not read as a write (workflow review P1, 2026-09-17).
  _bm_scan="$(printf '%s' "$1" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g" | sed -E 's/[[:space:]]#.*$//' \
    | sed -E 's/(^|[[:space:]])[0-9]?>[[:space:]]*\/dev\/null//g; s/(^|[[:space:]])&>[[:space:]]*\/dev\/null//g; s/[0-9]*>&[0-9]+//g')"
  printf '%s' "$_bm_scan" | grep -qE '(^|[;&|[:space:]])(sh|bash|zsh)[[:space:]]+-[A-Za-z]*c([[:space:]]|$)|(^|[;&|[:space:]])eval[[:space:]]|xargs[[:space:]]+(sh|bash)|<<[^|]*\|[[:space:]]*(sh|bash)([[:space:]]|$)' && return 0
  printf '%s' "$_bm_scan" | grep -qE 'git[[:space:]]+(push|commit|reset|checkout|clean|restore|stash)([[:space:]]|$)|(npm|pnpm|yarn|bun|pip3?)[[:space:]]+(install|i)([[:space:]]|$)|python3?[[:space:]]+-c([[:space:]]|$)|perl[[:space:]]+-[A-Za-z]*i|node[[:space:]]+(-e|--eval)([[:space:]]|$)|ruby[[:space:]]+-e([[:space:]]|$)|php[[:space:]]+-r([[:space:]]|$)|find[[:space:]][^|;]*-delete' && return 0
  # Addition over atom-floor: history- and tree-mutating git verbs it omits (workflow review P2).
  printf '%s' "$_bm_scan" | grep -qE 'git[[:space:]]+(merge|rebase|cherry-pick|apply|am|switch|tag|revert|branch[[:space:]]+-[dDmM])([[:space:]]|$)' && return 0
  printf '%s' "$_bm_scan" | grep -qE '(^|[;&|`[:space:]])(mv|cp|rm|rmdir|truncate|tee|install|touch|mkdir|ln|chmod|chown|rsync|patch|unzip|tar|dd)[[:space:]]|sed[[:space:]]+-+i|(sed|awk|gawk)[[:space:]][^|;]*--?in-?place|gawk[[:space:]]+-[A-Za-z]*i[[:space:]]+inplace|git[[:space:]]+(add|mv|rm)([[:space:]]|$)|tar[[:space:]]+[^|;]*x|(curl|wget)[[:space:]]([^|;]*[[:space:]])?-(o|O)([[:space:]]|$)|dd[[:space:]][^|;]*of=|(go|cargo)[[:space:]]+build|npx[[:space:]]|python3?[[:space:]]+[^-][^[:space:]]*\.py|sqlite3[[:space:]]|>\||&>|[0-9]?>>?' && return 0
  return 1
}

# sutra_steps_exempt_path <path> <sid> -> 0 when a Write/Edit target is exempt
# (D-A4: the artifact itself, session markers, memory files, enforcement logs).
sutra_steps_exempt_path() {
  # "contains" matches, so absolute and project-relative spellings both pass
  # (DeepSeek round-2 P1-7).
  case "$1" in
    *..*) return 1 ;;
    *".sutra/turn/$2/"*.lens.json|*".sutra/turn/$2/"*.cynefin.json) return 0 ;;   # the two artifacts only, never the lane files
    *".claude/sessions/$2/"*) return 0 ;;
    */.claude/projects/*/memory/*.md) return 0 ;;
    *".enforcement/"*) return 0 ;;
  esac
  return 1
}

# sutra_steps_exempt_bash <command> <sid> -> 0 when a Bash command is exempt
# (D-A6: it names the turn's artifact dir, or it IS the governance CLI).
sutra_steps_exempt_bash() {
  # Per SEGMENT (split on newline, ;, &&, ||, | - never inside quotes): a
  # segment is exempt when its first word is a governance CLI or it names
  # this turn's artifact dir. Row 1.1 semantics (2026-09-17): the command is
  # exempt when it has at least one MUTATING segment and every mutating
  # segment is exempt; read-only segments (`| wc -l`, `head`) ride along.
  # "git commit -m x\nbash holding/bin/sutra-atom close a-1" still fails:
  # the commit segment mutates and is not exempt.
  _eb_mut=0
  while IFS= read -r _eb_seg; do
    _eb_seg="$(printf '%s' "$_eb_seg" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    [ -n "$_eb_seg" ] || continue
    sutra_steps_bash_mutation "$_eb_seg" || continue
    _eb_mut=1
    case "$_eb_seg" in
      *..*) return 1 ;;
      *".sutra/turn/$2/"*.lens.json*|*".sutra/turn/$2/"*.cynefin.json*) continue ;;   # the two artifacts only
    esac
    _eb_first="$(printf '%s' "$_eb_seg" | sed -E 's/^(bash[[:space:]]+)?//' | awk '{print $1}')"
    case "$(basename "$_eb_first" 2>/dev/null)" in
      sutra-atom|sutra-dispatch|sutra-marker|sutra-steps|sutra-turn) continue ;;
    esac
    return 1
  done <<EOF
$(printf '%s\n' "$1" | awk '
  { n = length($0); q = ""; out = ""; esc = 0
    for (i = 1; i <= n; i++) { c = substr($0, i, 1)
      # shell quoting: no escapes inside single quotes; inside double quotes
      # only $ ` " \ are escapable; outside quotes any char is escapable
      if (esc) { esc = 0; if (q != "") c = " " }
      else if (c == "\\" && q != "\047") { nx = substr($0, i + 1, 1); if (q == "" || nx == "$" || nx == "`" || nx == "\"" || nx == "\\") esc = 1 }
      else if (q == "") { if (c == "\047" || c == "\"" || c == "`") q = c }
      else if (c == q) { q = "" }
      else if (c == ";" || c == "|" || c == "&") { c = " " }
      out = out c }
    gsub(/&&|\|\||;|\|/, "\n", out); print out }')
EOF
  [ "$_eb_mut" = "1" ]
}

# sutra_steps_latest_review <proj> <sid> <now_ts> -> prints the path of the
# newest done review.json (verdict present, ts within 1800 s of now) for the
# session, or nothing. Shared with hooks/codex-consult-gate.sh.
sutra_steps_latest_review() {
  # Corroborated only (workflow review P1, 2026-09-17): done, a real verdict,
  # fresh, the verdict repeated in the lane's review.md, a non-empty diff.
  _lr_dir="$1/.sutra/turn/$2"; _lr_now="${3:-0}"; case "$_lr_now" in ''|*[!0-9]*) _lr_now=0 ;; esac
  [ -d "$_lr_dir" ] || return 0
  for _lr_f in $(ls -t "$_lr_dir"/*.review.json 2>/dev/null); do
    _lr_v="$(jq -r --argjson now "$_lr_now" 'if .status == "done" and ((.verdict // "") | IN("PASS","CHANGES-REQUIRED")) and ($now - ((.ts // 0) | tonumber? // 0)) <= 1800 then .verdict else "" end' "$_lr_f" 2>/dev/null)"
    [ -n "$_lr_v" ] || continue
    _lr_t="$(basename "$_lr_f" .review.json)"
    if grep -qF "VERDICT: $_lr_v" "$_lr_dir/lane-logs/$_lr_t.review.md" 2>/dev/null && [ -s "$_lr_dir/lane-logs/$_lr_t.diff" ]; then
      printf '%s' "$_lr_f"; return 0
    fi
  done
  return 0
}

# sutra_steps_compute <proj> <sid> <turn> <opened_ts> -> prints the steps
# array as JSON, reading facts, markers, artifacts, the atom ledger and the
# tests marker. Never fails; unknown inputs become "missing"/"pending".
sutra_steps_compute() {
  _sc_proj="$1"; _sc_sid="$2"; _sc_turn="$3"; _sc_opened="${4:-0}"
  _sc_facts="$_sc_proj/.sutra/turn/$_sc_sid/$_sc_turn.facts.json"
  _sc_mdir="$_sc_proj/.claude/sessions/$_sc_sid"

  # 1-3 from facts
  _sc_f_classify="missing"; _sc_f_resolve="missing"; _sc_f_depth="missing"
  _sc_d_classify="no facts file"; _sc_d_resolve=""; _sc_d_depth=""
  if [ -f "$_sc_facts" ]; then
    # One TSV row; every field flattened to a single line first (DeepSeek round-2 P1-4),
    # and each of the three facts judged on its own key (P2-1).
    _sc_tsv="$(jq -r '
      def flat: tostring | gsub("[\\t\\n\\r]"; " ");
      [
        (((.classify.direction // "?") + " " + (.classify.verb // "?") + " " + (.classify.timing // "?") + " " + (.classify.channel // "?") + " " + (.classify.decision_risk // "?")) | flat),
        (((.resolve.resolution // "?") + " scope=" + (.resolve.scope // "?") + (if (.resolve.degraded // false) then " (degraded)" else "" end)) | flat),
        ((((.depth.n // 0) | tostring) + " " + (.depth.rubric // "?")) | flat),
        (if (.classify | type) == "object" then "1" else "0" end),
        (if (.resolve | type) == "object" then "1" else "0" end),
        (if (.depth | type) == "object" then "1" else "0" end)
      ] | @tsv' "$_sc_facts" 2>/dev/null | head -1)"
    if [ -n "$_sc_tsv" ]; then
      IFS=$'\t' read -r _sc_d_classify _sc_d_resolve _sc_d_depth _sc_has_cl _sc_has_re _sc_has_de <<< "$_sc_tsv"
      [ "$_sc_has_cl" = "1" ] && _sc_f_classify="done" || { _sc_f_classify="missing"; _sc_d_classify="classify.sh failed"; }
      [ "$_sc_has_re" = "1" ] && _sc_f_resolve="done"  || { _sc_f_resolve="missing";  _sc_d_resolve="no resolve in facts"; }
      [ "$_sc_has_de" = "1" ] && _sc_f_depth="done"    || { _sc_f_depth="missing";    _sc_d_depth="no depth in facts"; }
    fi
  fi

  # 4 placement
  _sc_f_place="pending"; _sc_d_place="marker placement-registered"
  if [ -f "$_sc_mdir/placement-registered" ]; then
    _sc_f_place="done"
    _sc_d_place="$(sed -n 's/^DOMAIN_REF=//p' "$_sc_mdir/placement-registered" 2>/dev/null | head -1)"
  fi

  # 5-6 artifacts
  _sc_f_lens="pending"; _sc_d_lens="-> $(sutra_artifact_rel "$_sc_sid" "$_sc_turn" lens)"
  _sc_lp="$(sutra_artifact_path "$_sc_proj" "$_sc_sid" "$_sc_turn" lens)"
  _sc_r="$(sutra_artifact_check "$_sc_lp" lens "$_sc_turn" "$_sc_sid" "$_sc_opened")"
  if [ "$_sc_r" = "ok" ]; then
    _sc_f_lens="done"
    _sc_d_lens="$(jq -r '((.pick // []) | join(",")) + " " + (.direction // "")' "$_sc_lp" 2>/dev/null)"
  elif [ "$_sc_r" != "missing" ]; then
    _sc_d_lens="invalid: $_sc_r"
  fi
  _sc_f_cyn="pending"; _sc_d_cyn="-> $(sutra_artifact_rel "$_sc_sid" "$_sc_turn" cynefin)"
  _sc_cp="$(sutra_artifact_path "$_sc_proj" "$_sc_sid" "$_sc_turn" cynefin)"
  _sc_r="$(sutra_artifact_check "$_sc_cp" cynefin "$_sc_turn" "$_sc_sid" "$_sc_opened")"
  if [ "$_sc_r" = "ok" ]; then
    _sc_f_cyn="done"
    _sc_d_cyn="$(jq -r '(.domain // "") + (if .human_gate then " human-gate" else "" end)' "$_sc_cp" 2>/dev/null)"
  elif [ "$_sc_r" != "missing" ]; then
    _sc_d_cyn="invalid: $_sc_r"
  fi

  # 7 blueprint: text gate, reported only
  _sc_f_bp="gated"; _sc_d_bp="blueprint-check.sh reads the reply"

  # 8 review: codex marker, or the runtime-run second lane (row 2) for this
  # session, or this turn's review.json while it runs
  _sc_f_codex="pending"; _sc_d_codex="marker codex-consulted or the review lane"
  if [ -f "$_sc_mdir/codex-consulted" ]; then _sc_f_codex="done"; _sc_d_codex="codex-consulted"
  elif [ -f "$_sc_proj/.sutra/turn/$_sc_sid/$_sc_turn.review.json" ]; then
    _sc_rv="$(jq -r '.status // "?"' "$_sc_proj/.sutra/turn/$_sc_sid/$_sc_turn.review.json" 2>/dev/null)"
    _sc_d_codex="review lane $_sc_rv"; [ "$_sc_rv" = "done" ] && _sc_f_codex="done"
  else
    # The lane finishes after its turn's Stop and the next prompt's reset wipes
    # session markers, so the verdict file is the durable evidence: the newest
    # done review in this session's turn dir, fresh within 1800 s (the same
    # window the codex consult ledger uses).
    _sc_rf="$(sutra_steps_latest_review "$_sc_proj" "$_sc_sid" "$_sc_opened")"
    if [ -n "$_sc_rf" ]; then
      _sc_f_codex="done"; _sc_d_codex="review lane $(jq -r '.verdict // "?"' "$_sc_rf" 2>/dev/null) (turn $(basename "$_sc_rf" .review.json | head -c 8))"
    fi
  fi

  # 9 atom
  _sc_f_atom="pending"; _sc_d_atom="no open atom"
  _sc_al="$_sc_proj/.sutra/atom-ledger.jsonl"
  if [ -f "$_sc_al" ]; then
    _sc_aid="$(jq -r --arg sid "$_sc_sid" -s '[.[] | select(.sid == $sid)] | group_by(.id) | map(last) | map(select(.status == "open")) | (last // {}) | .id // empty' "$_sc_al" 2>/dev/null)"
    [ -n "$_sc_aid" ] && { _sc_f_atom="open"; _sc_d_atom="$_sc_aid"; }
  fi

  # 10 tests: the marker (either spelling), or the runtime-run test lane (row 2)
  _sc_f_tests="pending"; _sc_d_tests="marker ran-tests or the test lane"
  if [ -f "$_sc_mdir/ran-tests" ] || [ -f "$_sc_mdir/tests-ran" ]; then _sc_f_tests="done"; _sc_d_tests="ran-tests"
  elif [ -f "$_sc_proj/.sutra/turn/$_sc_sid/$_sc_turn.tests.json" ]; then
    _sc_tv="$(jq -r '"\(.status // "?") exit=\(.exit // "-")"' "$_sc_proj/.sutra/turn/$_sc_sid/$_sc_turn.tests.json" 2>/dev/null)"
    _sc_d_tests="test lane $_sc_tv"
    case "$_sc_tv" in "done exit=0") _sc_f_tests="done" ;; "no-test-command"*) _sc_f_tests="missing"; _sc_d_tests="no test_command declared in .claude/sutra-project.json" ;; esac
  fi

  # 11 close
  _sc_f_close="pending"; _sc_d_close="at Stop"

  jq -nc \
    --arg s1 "$_sc_f_classify" --arg d1 "$_sc_d_classify" \
    --arg s2 "$_sc_f_resolve"  --arg d2 "$_sc_d_resolve" \
    --arg s3 "$_sc_f_depth"    --arg d3 "$_sc_d_depth" \
    --arg s4 "$_sc_f_place"    --arg d4 "$_sc_d_place" \
    --arg s5 "$_sc_f_lens"     --arg d5 "$_sc_d_lens" \
    --arg s6 "$_sc_f_cyn"      --arg d6 "$_sc_d_cyn" \
    --arg s7 "$_sc_f_bp"       --arg d7 "$_sc_d_bp" \
    --arg s8 "$_sc_f_codex"    --arg d8 "$_sc_d_codex" \
    --arg s9 "$_sc_f_atom"     --arg d9 "$_sc_d_atom" \
    --arg s10 "$_sc_f_tests"   --arg d10 "$_sc_d_tests" \
    --arg s11 "$_sc_f_close"   --arg d11 "$_sc_d_close" '[
      {n:1, id:"classify",  producer:"runtime", status:$s1,  detail:$d1},
      {n:2, id:"resolve",   producer:"runtime", status:$s2,  detail:$d2},
      {n:3, id:"depth",     producer:"runtime", status:$s3,  detail:$d3},
      {n:4, id:"placement", producer:"engine",  status:$s4,  detail:$d4},
      {n:5, id:"lens",      producer:"model",   status:$s5,  detail:$d5},
      {n:6, id:"cynefin",   producer:"model",   status:$s6,  detail:$d6},
      {n:7, id:"blueprint", producer:"model",   status:$s7,  detail:$d7},
      {n:8, id:"codex",     producer:"model",   status:$s8,  detail:$d8},
      {n:9, id:"atom",      producer:"runtime", status:$s9,  detail:$d9},
      {n:10, id:"tests",    producer:"runtime", status:$s10, detail:$d10},
      {n:11, id:"close",    producer:"runtime", status:$s11, detail:$d11}
    ]' 2>/dev/null
}

# sutra_steps_render <steps.json> -> the ASCII STEP TRACE table.
sutra_steps_render() {
  [ -f "$1" ] || { printf 'STEP TRACE: no ledger\n'; return 0; }
  jq -r '
    def pad(n): tostring | . + (" " * ((n - length) | if . < 0 then 0 else . end));
    "STEP TRACE turn \(((.turn_id // "unknown") | tostring)[0:8]) (adherence=\(.mode // "off"))",
    ((.steps // [])[] | "  \((.n // 0) | tostring | if length < 2 then " " + . else . end) \((.id // "?") | pad(10)) \((.producer // "?") | pad(8)) \((.status // "?") | pad(8)) \(.detail // "")"),
    (if ((.mutations // []) | length) > 0 then "  mutations: \((.mutations // []) | map(.decision // "?") | group_by(.) | map("\(.[0])=\(length)") | join(" "))" else empty end),
    (if .closed != null then "  closed: \(.closed.done)/11 done, refused \(.closed.refused), trace_pasted=\(.closed.trace_pasted)" else empty end)
  ' "$1" 2>/dev/null
}

# sutra_steps_render_stack <facts.json> <placement-marker-file> -> the block
# stack rendered from computed facts (adherence row 5 = MVP-2 render, W1-FAST-
# PATH s7): every computed field printed, every judgment field a <<FILL:x>>
# token. The Stop gates read INPUT:, TYPE: and DEPTH: N/5 at line start, so
# the compact lines keep those three at column 0. ASCII except the H-Sutra
# header's U+00B7 separator, which the header grammar requires.
sutra_steps_render_stack() {
  _rs_facts="$1"; _rs_pl="$2"
  [ -f "$_rs_facts" ] || { printf 'RENDERED STACK: no facts file for this turn\n'; return 0; }
  _rs_pline="unresolved (no-match)"
  if [ -f "$_rs_pl" ]; then
    _rs_p1="$(sed -n 's/^PLACEMENT: //p' "$_rs_pl" 2>/dev/null | head -1)"
    [ -n "$_rs_p1" ] && _rs_pline="$_rs_p1"
    _rs_dref="$(sed -n 's/^DOMAIN_REF=//p' "$_rs_pl" 2>/dev/null | head -1)"
    [ -z "$_rs_p1" ] && [ -n "$_rs_dref" ] && [ "$_rs_dref" != "unresolved" ] && _rs_pline="engine match $_rs_dref (compose the D-path from the placement context)"
  fi
  jq -r --arg pl "$_rs_pline" '
    def f(x): (x // "?");
    (.classify // {}) as $c | (.resolve // {}) as $r | (.depth // {}) as $d
    | ($c.direction // "INBOUND") as $dir | ($c.verb // "?") as $verb
    | (if ($c.tense // null) != null then " · TENSE:\($c.tense)" else "" end) as $tense
    | "RENDERED STACK (paste as your first lines, replace every <<FILL:x>>, keep computed fields as printed)",
      "[\($dir)·\($verb)\($tense) · TIMING:\(f($c.timing)) · CHANNEL:\(f($c.channel)) · REV:\(f($c.reversibility)) · RISK:\(f($c.decision_risk))]",
      "INPUT: <<FILL:input>>",
      "TYPE: \(f(.type)) | HOME: <<FILL:home>> | ROUTE: <<FILL:route>> | FIT: <<FILL:fit>> | ACTION: <<FILL:action>>",
      "DEPTH: \($d.n // 5)/5 | TASK: \"<<FILL:task>>\" | EFFORT: <<FILL:effort>> | COST: <<FILL:cost>> | IMPACT: <<FILL:impact>>",
      "FLOW: \(f(.type)) / \($dir).\($verb) | \(f($r.resolution)) scope=\(f($r.scope)) | steps <<FILL:steps>> | lens <<FILL:lens>> | cynefin <<FILL:cynefin>> | close <<FILL:close>>",
      "PLACEMENT: \($pl)"
  ' "$_rs_facts" 2>/dev/null
}

# sutra_steps_prompts <lens-status> <cynefin-status> -> the two judgment
# prompts, printed only for the steps still pending (adherence row 3 = skill
# injection: the runtime brings the skill's core to the step, so doing it is
# not a choice the model makes).
sutra_steps_prompts() {
  if [ "$1" != "done" ]; then
    printf 'LENS (core:lens, do it now, then write the lens artifact): mint 3-6 axes as interrogative x mechanism (who/what/when/where/why/how crossed with the unit'"'"'s parts, flows, states, owners); keep only the axes that change a decision; direction DOWN = decompose the unit along them, UP = generalize to the rule, ACROSS = reframe.\n'
  fi
  if [ "$2" != "done" ]; then
    printf 'CYNEFIN (core:cynefin, do it now, then write the cynefin artifact): clear = known method, fixed sequence, no gate; complicated = expert analysis first, review before commit; complex = parallel probes, small safe steps, human gate mandatory; chaotic = act to stabilize, then escalate. Name the domain, the shape, and whether a human gate is mandatory.\n'
  fi
}
