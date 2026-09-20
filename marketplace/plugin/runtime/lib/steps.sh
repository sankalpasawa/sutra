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

# row 6: the seal library rides with this one (D-A14); absent -> nothing
# verifies, which fails closed.
if [ -z "${SUTRA_SEAL_LOADED:-}" ] && [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/seal.sh" ]; then
  . "$(dirname "${BASH_SOURCE[0]}")/seal.sh" 2>/dev/null && SUTRA_SEAL_LOADED=1
fi

# sutra_steps_write <path> <json>: atomic replace.
sutra_steps_write() {
  _sw_tmp="$1.tmp.$$"
  if printf '%s\n' "$2" > "$_sw_tmp" 2>/dev/null; then
    mv -f "$_sw_tmp" "$1" 2>/dev/null
  fi
}

# _sutra_steps_bash_regex <text> -> 0 when a verb regex says it mutates. The
# three regexes are hooks/atom-floor.sh's, verbatim (2026-09-16). Since
# 2.285.1 this is the first of two passes: sutra_steps_bash_shape is the
# second (brief ADHERENCE-ROW6 s3.6, D-A16: class by shape, fail closed).
_sutra_steps_bash_regex() {
  # Quote/comment strip, then atom-floor.sh:95's noise pass (N>/dev/null, &>/dev/null,
  # N>&M) so a diagnostic redirect is not read as a write (workflow review P1, 2026-09-17).
  _bm_scan="$(printf '%s' "$1" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g" | sed -E 's/[[:space:]]#.*$//' \
    | sed -E 's/(^|[[:space:]])[0-9]?>[[:space:]]*\/dev\/null//g; s/(^|[[:space:]])&>[[:space:]]*\/dev\/null//g; s/[0-9]*>&[0-9]+//g')"
  printf '%s' "$_bm_scan" | grep -qE '(^|[;&|[:space:]])(sh|bash|zsh)[[:space:]]+-[A-Za-z]*c([[:space:]]|$)|(^|[;&|[:space:]])eval[[:space:]]|xargs[[:space:]]+(sh|bash)|<<[^|]*\|[[:space:]]*(sh|bash)([[:space:]]|$)' && return 0
  printf '%s' "$_bm_scan" | grep -qE 'git[[:space:]]+(push|commit|reset|checkout|clean|restore|stash)([[:space:]]|$)|(npm|pnpm|yarn|bun|pip3?)[[:space:]]+(install|i)([[:space:]]|$)|python3?[[:space:]]+-c([[:space:]]|$)|perl[[:space:]]+-[A-Za-z]*i|node[[:space:]]+(-e|--eval)([[:space:]]|$)|ruby[[:space:]]+-e([[:space:]]|$)|php[[:space:]]+-r([[:space:]]|$)|find[[:space:]][^|;]*-delete' && return 0
  # Addition over atom-floor: history- and tree-mutating git verbs it omits (workflow review P2).
  printf '%s' "$_bm_scan" | grep -qE 'git[[:space:]]+(merge|rebase|cherry-pick|apply|am|switch|tag|revert|branch[[:space:]]+-[dDmM])([[:space:]]|$)' && return 0
  printf '%s' "$_bm_scan" | grep -qE '(^|[;&|`[:space:]])(mv|cp|rm|rmdir|truncate|tee|install|touch|mkdir|ln|chmod|chown|rsync|patch|unzip|tar|dd)[[:space:]]|sed[[:space:]]+-+i|(sed|awk|gawk)[[:space:]][^|;]*--?in-?place|gawk[[:space:]]+-[A-Za-z]*i[[:space:]]+inplace|git[[:space:]]+(add|mv|rm)([[:space:]]|$)|tar[[:space:]]+[^|;]*x|(curl|wget)[[:space:]]([^|;]*[[:space:]])?-(o|O)([[:space:]]|$)|dd[[:space:]][^|;]*of=|(go|cargo)[[:space:]]+build|npx[[:space:]]|python3?[[:space:]]+[^-][^[:space:]]*\.py|sqlite3[[:space:]]|>\||&>|[0-9]?>>?' && return 0
  # 2.285.1 (workflow wf_1dc20d5c P1-3): read-listed traversal tools that run programs.
  printf '%s' "$_bm_scan" | grep -qE 'find[[:space:]][^|;]*-(exec|execdir|ok|okdir)([[:space:]]|$)|(^|[;&|[:space:]])(awk|gawk|nawk|mawk)[[:space:]][^|;]*system[[:space:]]*\(|xargs[[:space:]][^|;]*(sh|bash|zsh|python3?|node|perl|ruby|php)([[:space:]]|$)|(^|[;&|[:space:]])sed[[:space:]][^|;]*[/;]e[[:space:]]*$|(^|[;&|[:space:]])sort[[:space:]][^|;]*-o[[:space:]]' && return 0
  # 2.285.1: remote-state and tree-writing verbs of the CLIs the shape pass names as reads.
  printf '%s' "$_bm_scan" | grep -qE '(^|[;&|[:space:]])git[[:space:]]+(clone|pull|submodule[[:space:]]+(update|add)|worktree[[:space:]]+(add|remove)|init)([[:space:]]|$)|(^|[;&|[:space:]])gh[[:space:]]+[a-z-]+[[:space:]]+(create|edit|merge|close|delete|comment|review|sync|set|add|remove)([[:space:]]|$)|(^|[;&|[:space:]])claude[[:space:]]+plugin[[:space:]]+(update|install|uninstall|enable|disable)([[:space:]]|$)|(^|[;&|[:space:]])(brew|apt|apt-get|port|gem|cargo|go)[[:space:]]+(install|uninstall|remove|upgrade|get)([[:space:]]|$)' && return 0
  return 1
}

# sutra_steps_bash_shape <segment> -> 0 mutation, 1 read. Classes ONE segment by
# its first word (2.285.1, brief s3.6, D-A16): a shell or interpreter with any
# argument, heredoc or stdin is a mutation (`bash x.sh`, `./x`, `source x`,
# `make`, `python3 - <<EOF`); a first word on the read list is a read (the verb
# regexes still decide its redirects and verbs); anything else is a mutation.
sutra_steps_bash_shape() {
  # shell grouping and keywords are not programs (workflow wf_1dc20d5c P1-4):
  # strip leading ( { ! [[ and if/then/else/elif/fi/for/while/until/do/done/
  # case/esac, and trailing ) } tokens, then peel VAR=value and wrappers.
  _sh="$(printf '%s' "$1" | sed -E 's/^[[:space:]]+//; s/[[:space:]]*[)}]+[[:space:]]*$//')"
  _sh_n=0
  while [ $_sh_n -lt 10 ]; do
    _sh_n=$((_sh_n + 1))
    _sh2="$(printf '%s' "$_sh" | sed -E 's/^[({!]+[[:space:]]*//; s/^\[\[[[:space:]].*//; s/^for[[:space:]]+[A-Za-z_][A-Za-z0-9_]*([[:space:]]+in([[:space:]].*)?)?$//; s/^case[[:space:]]+.*[[:space:]]in$//; s/^(if|then|else|elif|fi|for|while|until|do|done|case|esac|in|select)([[:space:]]+|$)//; s/^[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+//; s/^(env|sudo|doas|time|nohup|command|exec|builtin|nice|caffeinate)([[:space:]]+-[^[:space:]]+)*[[:space:]]+//')"
    [ "$_sh2" = "$_sh" ] && break
    _sh="$_sh2"
  done
  _sh_first="$(printf '%s' "$_sh" | awk '{print $1}' | sed -E "s/^['\"]//; s/['\"]\$//")"
  _sh_rest="$(printf '%s' "$_sh" | awk '{$1=""; print}' | sed -E 's/^[[:space:]]+//')"
  [ -n "$_sh_first" ] || return 1
  # a bare assignment, a builtin, a keyword left alone: reads
  case "$_sh_first" in
    [A-Za-z_]*=*|export|set|unset|local|declare|typeset|readonly|shift|:|return|break|continue|wait|true|false|then|do|done|fi|esac|else|read) return 1 ;;
  esac
  # awk programs that spawn: the regex pass cannot see inside quotes (case 15)
  case "$(basename "$_sh_first" 2>/dev/null)" in
    awk|gawk|nawk|mawk) printf '%s' "$_sh_rest" | grep -qE 'system[[:space:]]*\(|\|[[:space:]]*"?(sh|bash)' && return 0 ;;
  esac
  # a version or help flag alone is a read, whatever the program (DeepSeek 2.285.1 s5)
  case "$_sh_rest" in -V|-v|--version|-version|-h|--help|version|help) return 1 ;; esac
  # a relative script path IS the program: ./x, ../x (DeepSeek 2.285.1 P1-1);
  # an absolute path is judged by its basename below (/usr/bin/git is git)
  case "$_sh_first" in ./*|../*) return 0 ;; esac
  _sh_base="$(basename "$_sh_first" 2>/dev/null)"
  case "$_sh_base" in
    sh|bash|zsh|ksh|dash|fish|python|python2|python3|python3.*|node|nodejs|perl|ruby|php|source|.|make|npm|pnpm|yarn|bun|npx|deno|tsx|ts-node|gradle|mvn|cargo|go|swift|osascript|expect|pip|pip3)
      [ -z "$_sh_rest" ] && return 1
      # read-only forms of the interpreters and package tools (workflow P2-4)
      case "$_sh_base:$_sh_rest" in
        sh:-n\ *|bash:-n\ *|zsh:-n\ *|python*:-m\ json.tool*|python*:-m\ py_compile*|python*:-m\ pytest*|python*:-m\ unittest*|python*:-m\ pip\ list*|python*:-m\ pip\ show*|python*:-m\ pip\ freeze*|npm:ls*|npm:view*|npm:outdated*|npm:audit|npm:why*|pip*:list*|pip*:show*|pip*:freeze*|cargo:check*|cargo:test*|cargo:clippy*|cargo:tree*|cargo:metadata*|go:vet*|go:test*|go:list*|go:env*|make:-n*|make:--dry-run*) return 1 ;;
      esac
      return 0 ;;
    ls|cat|head|tail|wc|grep|egrep|fgrep|rg|ugrep|ag|find|jq|yq|test|\[|echo|printf|true|false|pwd|cd|date|env|printenv|which|type|command|basename|dirname|realpath|readlink|stat|file|du|df|ps|uptime|sort|uniq|cut|tr|awk|gawk|sed|diff|cmp|comm|md5|md5sum|shasum|sha256sum|less|more|column|paste|seq|expr|bc|sleep|nl|tac|rev|fold|fmt|uname|hostname|whoami|id|open|tree|xxd|od|strings|hexdump|tput|clear|man|say|pbpaste|sw_vers|sysctl|lsof|netstat|ifconfig|ping|dig|nslookup|host|curl|wget|git|gh|claude|codex|rtk|xargs|sutra-steps|sutra-atom|sutra-dispatch|sutra-marker|sutra-turn|sutra-charcap|sutra-native|wdp-evidence|python3-config)
      return 1 ;;   # named read: the verb regexes decide its redirects and verbs
  esac
  return 0        # unknown first word: a mutation until proven otherwise (D-A16)
}

# sutra_steps_bash_segments <command>: one segment per line. Quotes are honoured
# by the row-1.1 awk masker (shell quoting rules), then the text is split on
# newline ; && || |.
sutra_steps_bash_segments() {
  # 2.285.1 (workflow wf_1dc20d5c P1-1): a single & (background) separates
  # segments too, after fd redirects (2>&1, &>) are masked; $( and backticks
  # open a new segment so `VAR=$(bash x.sh)` shows its inner command.
  printf '%s\n' "$1" | awk '
  { n = length($0); q = ""; out = ""; esc = 0
    for (i = 1; i <= n; i++) { c = substr($0, i, 1)
      # shell quoting: no escapes inside single quotes; inside double quotes
      # only $ ` " \ are escapable; outside quotes any char is escapable
      if (esc) { esc = 0; if (q != "") c = " " }
      else if (c == "\\" && q != "\047") { nx = substr($0, i + 1, 1); if (q == "" || nx == "$" || nx == "`" || nx == "\"" || nx == "\\") esc = 1 }
      else if (q == "") { if (c == "\047" || c == "\"") q = c }
      else if (c == q) { q = "" }
      else if (c == ";" || c == "|" || c == "&") { c = " " }
      out = out c }
    gsub(/[0-9]*>&[0-9]+/, " ", out); gsub(/&>>?/, ">", out)
    gsub(/&&|\|\||;|\||&|`|\$\(/, "\n", out); print out }'
}

# sutra_steps_bash_segment_mutation <segment> -> 0 when one segment mutates:
# the verb regexes first, then the shape.
sutra_steps_bash_segment_mutation() {
  _sm_seg="$(printf '%s' "$1" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  [ -n "$_sm_seg" ] || return 1
  _sutra_steps_bash_regex "$_sm_seg" && return 0
  sutra_steps_bash_shape "$_sm_seg"
}

# sutra_steps_bash_mutation <command> -> 0 when the command mutates, 1 when
# every segment is a read. Whole-command regexes first (they span segments:
# `<<EOF | sh`), then each segment through regex + shape.
sutra_steps_bash_mutation() {
  _sutra_steps_bash_regex "$1" && return 0
  while IFS= read -r _bm_seg; do
    sutra_steps_bash_segment_mutation "$_bm_seg" && return 0
  done <<EOF
$(sutra_steps_bash_segments "$1")
EOF
  return 1
}

# sutra_steps_runtime_owned <text> -> 0 when the text names one of the runtime's
# own files (D-A15, 2.285.1): the override file, the flag files, the kill
# files, the seal dir, the session stamp. No tool call may name them.
sutra_steps_runtime_owned() {
  # quotes are stripped first, so `.sutra-over""rides` and '.sutra-'"overrides"
  # still name the file (DeepSeek 2.285.1 P1-2); deeper obfuscation is row 6.
  # row 6 (DeepSeek P1-3): the turn's facts, ledger and lane files are the
  # runtime's too - a model that deletes the facts file would blank the depth
  printf '%s' "$1" | tr -d '"'"'"'`' | grep -qE "$_SUTRA_RO_RE"
}
# the core names (switches, override file, seal dir, session stamp, the lane's
# connector keys - workflow row-6 P1-3) are refused wherever they appear in a
# write shape; the ledger and lane files join them for command text and for
# file_path targets, never for a document's payload (workflow P2-3)
_SUTRA_RO_RE_CORE='\.sutra-overrides|\.sutra-runtime-(adherence|markers|disabled)|\.sutra-runtime/|\.sutra-connectors/|\.config/deepseek/|\.sutra/turn/[^/[:space:]]+/opened([^A-Za-z0-9_-]|$)'
_SUTRA_RO_RE="$_SUTRA_RO_RE_CORE"'|\.sutra/turn/[^/[:space:]]+/[^/[:space:]]+\.(facts|steps|review|tests|verifies|truthdiff|progress)\.json|\.sutra/turn/[^/[:space:]]+/[^/[:space:]]+\.jsonl|\.sutra/turn/[^/[:space:]]+/lane-logs/'

# sutra_steps_runtime_owned_write <text> -> 0 when some LINE of the text names
# a runtime-owned file in a WRITE shape (workflow wf_1dc20d5c P1-5: a doc, a
# test or a grep that merely mentions the name is not a mutation of it): a
# redirect, a mutating verb, a script write call on the same line - or the
# seal dir at all, whose contents are secret.
sutra_steps_runtime_owned_write() {  # <text> [content]
  # content mode (a Write/Edit payload): the switch, override, seal, stamp and
  # connector names only - a doc or a cleanup script may name a ledger file
  # (workflow row-6 P2-3); command mode (default): every runtime-owned name
  _ow_re="$_SUTRA_RO_RE"; [ "${2:-}" = "content" ] && _ow_re="$_SUTRA_RO_RE_CORE"
  _ow="$(printf '%s' "$1" | tr -d '"'"'"'`')"
  # the seal dir: any read or copy of it is a hit too (its contents are secret)
  printf '%s\n' "$_ow" | grep -E '\.sutra-runtime/' | grep -qE '(^|[[:space:]|;&(])(cat|less|more|head|tail|xxd|od|base64|cp|cut|strings|hexdump|python3?|node|perl|ruby|source|\.)[[:space:]]|open[[:space:]]*\(|read[[:space:]]*\(|readFile|read_text|readlink' && return 0
  printf '%s\n' "$_ow" | grep -E "$_ow_re" \
    | grep -qE '>|(^|[[:space:]|;&(])(tee|rm|mv|cp|touch|chmod|chown|ln|truncate|install|dd|rsync|unlink|shred)[[:space:]]|sed[[:space:]]+-+i|open[[:space:]]*\([^)]*[[:space:]]*,[[:space:]]*.?[wa]|\.write\(|\.write_text\(|write_text|os\.remove|os\.unlink|shutil\.|unlinkSync|writeFile|copyFile|rename\(|renameSync|Path\(|\.unlink\(|\.touch\(|>>'
}

# sutra_steps_exempt_path <path> <sid> -> 0 when a Write/Edit target is exempt
# (D-A4: the artifact itself, session markers, memory files, enforcement logs).
sutra_steps_exempt_path() {
  # "contains" matches, so absolute and project-relative spellings both pass
  # (DeepSeek round-2 P1-7).
  case "$1" in
    *..*) return 1 ;;
    *.sh|*.bash|*.zsh|*.py|*.js|*.mjs|*.ts|*.rb|*.pl|*.php) return 1 ;;   # 2.285.1: a script under an exempt dir is not exempt (brief s3.6)
    *".sutra/turn/$2/"*.lens.json|*".sutra/turn/$2/"*.cynefin.json|*".sutra/turn/$2/"*.blueprint.json|*".sutra/turn/$2/"*.build_layer.json|*".sutra/turn/$2/"*.placement.json|*".sutra/turn/$2/"*.depth.json) return 0 ;;   # the six judgment artifacts only, never the lane files
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
    sutra_steps_bash_segment_mutation "$_eb_seg" || continue
    _eb_mut=1
    case "$_eb_seg" in
      *..*) return 1 ;;
      *".sutra/turn/$2/"*.lens.json*|*".sutra/turn/$2/"*.cynefin.json*|*".sutra/turn/$2/"*.blueprint.json*|*".sutra/turn/$2/"*.build_layer.json*|*".sutra/turn/$2/"*.placement.json*|*".sutra/turn/$2/"*.depth.json*) continue ;;   # the six judgment artifacts only
    esac
    _eb_first="$(printf '%s' "$_eb_seg" | sed -E 's/^(bash[[:space:]]+)?//' | awk '{print $1}' | sed -E "s/^['\"]//; s/['\"]\$//")"
    case "$(basename "$_eb_first" 2>/dev/null)" in
      sutra-atom|sutra-dispatch|sutra-marker|sutra-steps|sutra-turn) continue ;;
    esac
    return 1
  done <<EOF
$(sutra_steps_bash_segments "$1")
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
  # row 6 (brief s3.5): sealed only, and bound to this or the previous turn of
  # the session (the newest two ledgers), never an older one.
  _lr_recent="$(ls -t "$_lr_dir"/*.steps.json 2>/dev/null | head -2 | sed -E 's|.*/||; s|\.steps\.json$||' | tr '\n' ' ')"
  for _lr_f in $(ls -t "$_lr_dir"/*.review.json 2>/dev/null); do
    _lr_v="$(jq -r --argjson now "$_lr_now" 'if .status == "done" and ((.verdict // "") | IN("PASS","CHANGES-REQUIRED")) and ($now - ((.ts // 0) | tonumber? // 0)) <= 1800 then .verdict else "" end' "$_lr_f" 2>/dev/null)"
    [ -n "$_lr_v" ] || continue
    _lr_t="$(basename "$_lr_f" .review.json)"
    case " $_lr_recent " in *" $_lr_t "*) ;; *) continue ;; esac
    command -v sutra_seal_verify >/dev/null 2>&1 && sutra_seal_verify "$_lr_f" || continue
    if grep -qF "VERDICT: $_lr_v" "$_lr_dir/lane-logs/$_lr_t.review.md" 2>/dev/null && [ -s "$_lr_dir/lane-logs/$_lr_t.diff" ]; then
      printf '%s' "$_lr_f"; return 0
    fi
  done
  return 0
}

# sutra_steps_path_category <path> <proj> <gates.json> -> one of runtime-owned |
# plugin-runtime | shared-runtime | holding-impl | legacy-hard | whitelist |
# soft | none (row 6: the D38 table as data). Project-relative or absolute
# under the project; a path outside the project is "none".
sutra_steps_path_category() {
  _pc_p="$1"; _pc_proj="$2"; _pc_rules="$3"
  [ -n "$_pc_p" ] || { printf 'none'; return 0; }
  sutra_steps_runtime_owned "$_pc_p" && { printf 'runtime-owned'; return 0; }
  case "$_pc_p" in
    "$_pc_proj"/*) _pc_p="${_pc_p#"$_pc_proj"/}" ;;
    /*) printf 'none'; return 0 ;;
  esac
  [ -f "$_pc_rules" ] || { printf 'soft'; return 0; }
  jq -r --arg p "$_pc_p" '
    .path_categories | to_entries[]
    | select(.key != "runtime-owned")
    | select(any(.value[]; . as $pre | ($p == $pre) or ($p | startswith($pre))))
    | .key' "$_pc_rules" 2>/dev/null | head -1 | { read -r _pc_c; printf '%s' "${_pc_c:-soft}"; }
}

# sutra_steps_lane_configured -> 0 when a second review lane can run on this
# box (a DeepSeek key file, or the codex CLI, or an explicit lane command).
sutra_steps_lane_configured() {
  # mirrors what review_lane.sh can actually run (workflow row-6 P1-5): an
  # executable lane command, or a DeepSeek key where deepseek-review.sh looks;
  # a codex binary is not a lane
  case "${SUTRA_LANE_CONFIGURED:-}" in 1) return 0 ;; 0) return 1 ;; esac   # explicit (tests, boxes without a lane)
  [ -n "${SUTRA_REVIEW_LANE_CMD:-}" ] && [ -x "${SUTRA_REVIEW_LANE_CMD}" ] && return 0
  [ -n "${DEEPSEEK_TOKEN_FILE:-}" ] && [ -s "${DEEPSEEK_TOKEN_FILE}" ] && return 0
  [ -n "${HOME:-}" ] && [ -s "$HOME/.sutra-connectors/oauth/deepseek.json" ] && return 0
  [ -n "${HOME:-}" ] && [ -s "$HOME/.config/deepseek/auth.token" ] && return 0
  return 1
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

  # 3b depth (row 6): the model may RAISE the rubric's number with depth.json;
  # a lower number is ignored and noted in the detail.
  _sc_dp="$(sutra_artifact_path "$_sc_proj" "$_sc_sid" "$_sc_turn" depth)"
  if [ -f "$_sc_dp" ] && [ "$(sutra_artifact_check "$_sc_dp" depth "$_sc_turn" "$_sc_sid" "$_sc_opened")" = "ok" ]; then
    _sc_dr="$(jq -r '.depth.n // 0' "$_sc_facts" 2>/dev/null)"; case "$_sc_dr" in ''|*[!0-9]*) _sc_dr=0 ;; esac
    _sc_dm="$(jq -r '.depth // 0' "$_sc_dp" 2>/dev/null)"; case "$_sc_dm" in ''|*[!0-9]*) _sc_dm=0 ;; esac
    if [ "$_sc_dm" -gt "$_sc_dr" ]; then _sc_d_depth="$_sc_dm (raised from $_sc_dr by depth.json)"
    else _sc_d_depth="$_sc_d_depth (depth.json $_sc_dm ignored: not a raise)"; fi
  fi

  # 4 placement: the engine's marker, or (row 6) the model's placement.json
  # when the engine found no match
  _sc_f_place="pending"; _sc_d_place="marker placement-registered"
  if [ -f "$_sc_mdir/placement-registered" ]; then
    # only the ENGINE's marker counts (SOURCE=engine); a model-written one is
    # no evidence (workflow row-6 P1-2) - the model answers with placement.json
    _sc_pl_src="$(sed -n 's/^SOURCE=//p' "$_sc_mdir/placement-registered" 2>/dev/null | head -1)"
    _sc_d_place="$(sed -n 's/^DOMAIN_REF=//p' "$_sc_mdir/placement-registered" 2>/dev/null | head -1)"
    if [ "$_sc_pl_src" = "engine" ]; then _sc_f_place="done"
    else _sc_d_place="$_sc_d_place (marker SOURCE=${_sc_pl_src:-none}: not evidence; write placement.json)"; fi
  fi
  _sc_pp="$(sutra_artifact_path "$_sc_proj" "$_sc_sid" "$_sc_turn" placement)"
  if [ -f "$_sc_pp" ] && [ "$(sutra_artifact_check "$_sc_pp" placement "$_sc_turn" "$_sc_sid" "$_sc_opened")" = "ok" ]; then
    _sc_f_place="done"; _sc_d_place="$(jq -r '.domain_ref' "$_sc_pp" 2>/dev/null) (placement.json)"
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

  # 7 blueprint (row 6, brief s3.3): the artifact, validated; its verify
  # commands run at Stop through the test lane. Manual-only verifies leave it
  # open, never done.
  _sc_f_bp="pending"; _sc_d_bp="-> $(sutra_artifact_rel "$_sc_sid" "$_sc_turn" blueprint)"
  _sc_bp="$(sutra_artifact_path "$_sc_proj" "$_sc_sid" "$_sc_turn" blueprint)"
  _sc_dn="$(jq -r '.depth.n // 0' "$_sc_facts" 2>/dev/null)"; case "$_sc_dn" in ''|*[!0-9]*) _sc_dn=0 ;; esac
  _sc_r="$(SUTRA_ARTIFACT_DEPTH="$_sc_dn" sutra_artifact_check "$_sc_bp" blueprint "$_sc_turn" "$_sc_sid" "$_sc_opened")"
  if [ "$_sc_r" = "ok" ]; then
    _sc_bpv="$(jq -r '[(.steps | length), ([.steps[] | select(.verify.kind == "cmd")] | length)] | "\(.[0]) steps, \(.[1]) runnable verifies"' "$_sc_bp" 2>/dev/null)"
    if jq -e '[.steps[] | select(.verify.kind == "cmd")] | length > 0' "$_sc_bp" >/dev/null 2>&1; then _sc_f_bp="done"; else _sc_f_bp="open"; fi
    _sc_d_bp="$_sc_bpv"
  elif [ "$_sc_r" != "missing" ]; then
    _sc_d_bp="invalid: $_sc_r"
  fi

  # 8 review (row 6, brief s3.5, workflow P1-4): ONLY a sealed lane verdict
  # counts - this turn's review.json once sealed, or the newest sealed and
  # fresh verdict of this session bound to this or the previous turn. The
  # codex-consulted marker is a model-writable file and is no evidence.
  _sc_f_codex="pending"; _sc_d_codex="the review lane (sealed verdict)"
  _sc_rj="$_sc_proj/.sutra/turn/$_sc_sid/$_sc_turn.review.json"
  if [ -f "$_sc_rj" ]; then
    _sc_rv="$(jq -r '.status // "?"' "$_sc_rj" 2>/dev/null)"
    if [ "$_sc_rv" = "done" ]; then
      if command -v sutra_seal_verify >/dev/null 2>&1 && sutra_seal_verify "$_sc_rj"; then
        _sc_f_codex="done"; _sc_d_codex="review lane $(jq -r '.verdict // "?"' "$_sc_rj" 2>/dev/null) (sealed)"
      else
        _sc_d_codex="review lane done but UNSEALED: not evidence"
      fi
    else
      _sc_d_codex="review lane $_sc_rv"
    fi
  else
    _sc_rf="$(sutra_steps_latest_review "$_sc_proj" "$_sc_sid" "$_sc_opened")"
    if [ -n "$_sc_rf" ]; then
      _sc_f_codex="done"; _sc_d_codex="review lane $(jq -r '.verdict // "?"' "$_sc_rf" 2>/dev/null) (sealed, turn $(basename "$_sc_rf" .review.json | head -c 8))"
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

# sutra_steps_render_pretty <steps.json> -> the human-readable table the Stop
# step prints (founder, 2026-09-18: "beautiful, concise, but human-readable").
# One header line with the counts, one row per step with a checkbox glyph:
# [x] done, [o] open, [~] gated, [ ] pending, [!] missing. ASCII only.
sutra_steps_render_pretty() {
  [ -f "$1" ] || { printf 'sutra: no ledger for this turn\n'; return 0; }
  jq -r '
    def pad(n): tostring | . + (" " * ((n - length) | if . < 0 then 0 else . end));
    def glyph: if . == "done" then "[x]" elif . == "open" then "[o]" elif . == "gated" then "[~]" elif . == "missing" then "[!]" else "[ ]" end;
    def trim(n): tostring | if length > n then .[0:n-3] + "..." else . end;
    ((.steps // []) | map(select(.status == "done" or .status == "open")) | length) as $done |
    ((.mutations // []) | map(select(.decision == "deny")) | length) as $refused |
    ((.mutations // []) | map(select(.decision == "warn")) | length) as $warned |
    ((.mutations // []) | map(select(.decision == "allow")) | length) as $allowed |
    "sutra turn \(((.turn_id // "unknown") | tostring)[0:8])   done \($done)/\((.steps // []) | length)   edits \($allowed)   refused \($refused)\(if $warned > 0 then "   warned \($warned)" else "" end)\(if .closed != null and .closed.trace_pasted == false then "   trace not pasted" else "" end)",
    ((.steps // [])[] | "  \((.status // "") | glyph) \((.id // "?") | pad(10)) \((.detail // "") | trim(64))")
  ' "$1" 2>/dev/null
  sutra_steps_render_bp "$1"
}

# sutra_steps_bp_state <steps.json> -> one JSON object {source, total, done,
# steps:[{n, status, do}]} for the blueprint's own steps, or nothing. Source
# "verifies" = the sealed Stop lane result (truth); "progress" = the live
# PostToolUse hint (row 6.2); the blueprint's `do` texts ride along.
sutra_steps_bp_state() {
  _bs_base="${1%.steps.json}"
  _bs_bp="$_bs_base.blueprint.json"; _bs_v="$_bs_base.verifies.json"; _bs_p="$_bs_base.progress.json"
  [ -f "$_bs_bp" ] || return 0
  if [ -f "$_bs_v" ] && jq -e '.status == "done"' "$_bs_v" >/dev/null 2>&1; then
    jq -c --slurpfile bp "$_bs_bp" '
      ($bp[0].steps // []) as $s
      | {source:"verifies", total:($s|length), done:.passed,
         steps:[ .results[] | {n, status:(if .exit == 0 then "done" elif .exit == null then "manual" else "failed" end), do:($s[.n-1].do // "")} ]}' "$_bs_v" 2>/dev/null
  elif [ -f "$_bs_p" ]; then
    jq -c --slurpfile bp "$_bs_bp" '
      ($bp[0].steps // []) as $s
      | {source:"progress", total:.total, done:.done,
         steps:[ .steps[] | {n, status, do:($s[.n-1].do // "")} ]}' "$_bs_p" 2>/dev/null
  else
    jq -c '{source:"none", total:(.steps|length), done:0, steps:[ .steps | to_entries[] | {n:(.key+1), status:"pending", do:.value.do} ]}' "$_bs_bp" 2>/dev/null
  fi
}

# sutra_steps_render_bp <steps.json> -> the blueprint's own steps under the
# 11 rows: "  blueprint steps 2/3 (live)" then one "[x] n) do" row each.
sutra_steps_render_bp() {
  _rb="$(sutra_steps_bp_state "$1")"
  [ -n "$_rb" ] || return 0
  printf '%s' "$_rb" | jq -r '
    def glyph: if . == "done" then "[x]" elif . == "failed" then "[!]" elif . == "slow" then "[~]" elif . == "manual" then "[m]" else "[ ]" end;
    def trim(n): tostring | gsub("\n"; " ") | if length > n then .[0:n-3] + "..." else . end;
    "  blueprint steps \(.done)/\(.total)\(if .source == "verifies" then " (sealed at Stop)" elif .source == "progress" then " (live)" else "" end)",
    (.steps[] | "      \(.status | glyph) \(.n)) \(.do | trim(58))")
  ' 2>/dev/null
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
  # row 6: the third argument is the blueprint status; its prompt names the
  # artifact and the runnable-verify rule (brief s3.3).
  if [ "${3:-pending}" != "done" ]; then
    printf 'BLUEPRINT (core:blueprint, do it now, then write the blueprint artifact TURN.blueprint.json): doing, 1+ steps each with a verify the runtime can RUN at Stop ({kind:"cmd",cmd:"<shell check>"}; kind "manual" is allowed but counts as open, never done; at depth 3+ every step verify must be cmd), output (what the result looks like), verified_by {kind,cmd} spanning all steps, stops_if. The reply'"'"'s BLUEPRINT block is rendered from this file, so the two cannot disagree.\n'
  fi
  if [ "$1" != "done" ]; then
    printf 'LENS (core:lens, do it now, then write the lens artifact): mint 3-6 axes as interrogative x mechanism (who/what/when/where/why/how crossed with the unit'"'"'s parts, flows, states, owners); keep only the axes that change a decision; direction DOWN = decompose the unit along them, UP = generalize to the rule, ACROSS = reframe.\n'
  fi
  if [ "$2" != "done" ]; then
    printf 'CYNEFIN (core:cynefin, do it now, then write the cynefin artifact): clear = known method, fixed sequence, no gate; complicated = expert analysis first, review before commit; complex = parallel probes, small safe steps, human gate mandatory; chaotic = act to stabilize, then escalate. Name the domain, the shape, and whether a human gate is mandatory.\n'
  fi
}
