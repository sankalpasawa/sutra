#!/usr/bin/env bash
# LAYER=L1
# SCOPE=single-instance:asawa-holding
# TARGET_PATH=holding/hooks/atom-floor.sh
# WHY_NOT_L0_KIND=staging
# WHY_NOT_L0_REASON=Atom floor stages in asawa-holding before plugin L0 per FR P6
# PROMOTE_TO=sutra/marketplace/plugin/hooks/atom-floor.sh
# PROMOTE_BY=2026-08-31
# OWNER=Governance Hooks charter
# ACCEPTANCE=atom-v0-test all-PASS incl. HARD block + whitelist cases
# TS=2026-08-01
#
# atom-floor.sh — Work-Atom arming floor + observation journal (FR C3+C4).
# MODE: HARD (founder direction 2026-08-01 — SOFT window skipped, "till I say
# otherwise"). Sourced by dispatcher-pretool.sh. This function NEVER exits
# non-zero itself; it sets ATOM_FLOOR_VERDICT=allow|block and the dispatcher
# converts "block" to BLOCK_CODE=2. Fail-open on internal error.
# Whitelist (journal-only, never block) mirrors build-layer whitelist +
# codex 2026-08-01 additions: .git, tmp/scratchpad, plugin caches.
# Kill-switches: touch ~/.atom-floor-disabled  OR  ATOM_FLOOR_DISABLED=1.

# Whitelist test shared by both branches. Returns 0 if the path is exempt.
_atom_floor_whitelisted() {
  case "$1" in
    */.claude/*|.claude/*|*/.enforcement/*|.enforcement/*|*/.sutra/*|.sutra/*| \
    */.git/*|.git/*|*/holding/checkpoints/*|holding/checkpoints/*| \
    */holding/TODO.md|holding/TODO.md|*hook-log.jsonl|"$HOME"/.claude/*| \
    /private/tmp/*|/tmp/*|*/node_modules/*|node_modules/*|*/.tmp/*|.tmp/*|*/dev/null*) return 0 ;;
    *) return 1 ;;
  esac
}

atom_floor_check() {
  # $1 = TOOL_NAME  $2 = FILE_PATH (may be empty)  $3 = BASH_CMD (Bash tool only)
  ATOM_FLOOR_VERDICT="allow"
  {
    local tool="${1:-}" fpath="${2:-}" cmd="${3:-}"
    [ -f "$HOME/.atom-floor-disabled" ] && return 0
    [ "${ATOM_FLOOR_DISABLED:-0}" = "1" ] && return 0

    local root sid state ts open_atom mode="" target=""
    root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
    sid="${CLAUDE_CODE_SESSION_ID:-nosession}"
    state="$root/.sutra/atoms/$sid"
    ts=$(date +%s)

    case "$tool" in
      Edit|Write)
        mode="HARD"; target="${fpath##*/}"
        _atom_floor_whitelisted "$fpath" && return 0
        ;;
      Bash)
        # HARD-BASH branch (founder 2026-08-01 "don't skip anything"; codex-consulted).
        # W1 rework (WDP W1-T10/T11/T12, dual-reviewed at G1): scan a COPY with
        # quoted segments removed (quoted text is data — kills in-quote verbs,
        # in-quote redirects, and prompt-text paths), comment tail stripped, and
        # noise redirects (2>/dev/null, 2>&1, N>/dev/null, &>/dev/null) deleted.
        [ -z "$cmd" ] && return 0
        mode="HARD-BASH"; target="bash-cmd"
        local cmd_scan
        # W6 FP-replay #5: heredoc BODIES are data, not command targets —
        # strip them before token scan (same precedent as quoted-segment
        # removal: prose like 'skill/hook' in a heredoc must not gate).
        # awk drops lines between <<[-]WORD and the terminator line WORD.
        # G5 codex P1 (+ own fix): a quoted "<<EOF" is DATA and must not open a
        # heredoc, but `<<'EOF'` IS the common real opener — so ordering cannot
        # solve it. Decide by QUOTE PARITY of the text before the `<<`: even =
        # real shell syntax, odd = inside a string. Heredoc pass runs on raw
        # text (delimiter intact), quote-strip after.
        # FP-replay #11: keep the heredoc-stripped text WITH quotes intact in
        # its own variable — the quoted-target recovery below must read this,
        # not raw $cmd, or it harvests JSON string values out of heredoc bodies
        # ("path":"other/file.md") and gates them as mutation targets.
        local cmd_nohd
        cmd_nohd=$(printf '%s' "$cmd" | awk '
          function parity(s,   i,c,sq,dq) {
            for (i=1; i<=length(s); i++) { c=substr(s,i,1)
              if (c=="\"" && sq%2==0) dq++; else if (c=="'"'"'" && dq%2==0) sq++ }
            return (sq%2) + (dq%2) }
          !inhd { if (match($0, /<<-?[[:space:]]*["'"'"']?[A-Za-z_][A-Za-z0-9_]*/) \
                     && parity(substr($0, 1, RSTART-1)) == 0) {
                    t=substr($0, RSTART+2); sub(/^-?[[:space:]]*["'"'"']?/,"",t);
                    sub(/[^A-Za-z0-9_].*$/,"",t); inhd=1; print; next }
                  print; next }
          inhd  { line=$0; sub(/^[[:space:]]+/,"",line);
                  if (line == t) { inhd=0 } next }')
        cmd_scan=$(printf '%s' "$cmd_nohd" \
          | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g" \
          | sed -E 's/^[[:space:]]*#.*$//; s/[[:space:]]#.*$//' \
          | sed -E 's/(^|[;&|])[[:space:]]*cd[[:space:]]+[^;&|[:space:]$`<>]+/\1 /g' \
          | sed -E 's/(^|[[:space:]])[0-9]?>[[:space:]]*\/dev\/null//g; s/(^|[[:space:]])&>[[:space:]]*\/dev\/null//g; s/[0-9]*>&[0-9]+//g')
        # Exempt-by-name ANCHORED as a command word (d2a fix): start or after
        # ;|&( separators, optional env assignments, optional command/exec/env,
        # optional (ba)sh + path prefix. Substring-anywhere exemption is dead.
        # G5 codex P1: exemption applies only when EVERY segment of a compound
        # command is an exempt CLI — `sutra-dispatch show; echo x > other/f`
        # used to exempt the whole line and hand the gate zero targets.
        _af_exempt_re='^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]+[[:space:]]+)*(command[[:space:]]+|exec[[:space:]]+|env[[:space:]]+)?((ba)?sh[[:space:]]+)?([^[:space:]]*/)?(sutra-atom|sutra-marker|sutra-dispatch|routing-policy-resolve|context-manifest|flow-ledger-append|wdp-evidence|rtk)([[:space:]]|$)'
        if printf '%s' "$cmd_scan" | grep -qE "$_af_exempt_re"; then
          local _af_all_exempt=1 _af_seg
          while IFS= read -r _af_seg; do
            [ -z "${_af_seg//[[:space:]]/}" ] && continue
            printf '%s' "$_af_seg" | grep -qE "$_af_exempt_re" || { _af_all_exempt=0; break; }
            # printf '%s\n' (NOT '%s') — without the trailing newline `read`
            # silently drops the LAST segment, which is exactly where the
            # mutator hides in `<exempt-cli>; <mutator>` (caught end-to-end).
          done < <(printf '%s\n' "$cmd_scan" | tr ';&|\n' '\n\n\n\n')
          [ "$_af_all_exempt" = "1" ] && return 0
        fi
        # Shell-eval wrappers + heredoc-to-shell = mutator requiring an atom [codex].
        # T18 codex P1 fold: option GROUPS containing c (bash -lc, sh -ec, zsh -fc)
        # count as wrappers — quote-stripping made the bare '-c' match insufficient.
        local is_wrapper=0
        printf '%s' "$cmd_scan" | grep -qE '(^|[;&|[:space:]])(sh|bash|zsh)[[:space:]]+-[A-Za-z]*c([[:space:]]|$)|(^|[;&|[:space:]])eval[[:space:]]|xargs[[:space:]]+(sh|bash)|<<[^|]*\|[[:space:]]*(sh|bash)([[:space:]]|$)' && is_wrapper=1
        # G6 fold: the dispatch gate needs to know a mutation WAS identified
        # even when no target could be named — otherwise an unnameable mutation
        # (`git reset`, `python -c`, an installer) reaches the gate with zero
        # targets and is waved through. Wrappers count as mutations too.
        ATOM_FLOOR_MUTATION=0
        [ "$is_wrapper" = "1" ] && ATOM_FLOOR_MUTATION=1
        if [ "$is_wrapper" = "0" ]; then
          local suspicious=0 tok
          # Path-INDEPENDENT mutators gate directly [codex + B7]; W1-T12 adds
          # opaque-target interpreters + find -delete + git clean/restore/stash.
          if printf '%s' "$cmd_scan" | grep -qE 'git[[:space:]]+(push|commit|reset|checkout|clean|restore|stash)([[:space:]]|$)|(npm|pnpm|yarn|bun|pip3?)[[:space:]]+(install|i)([[:space:]]|$)|python3?[[:space:]]+-c([[:space:]]|$)|perl[[:space:]]+-[A-Za-z]*i|node[[:space:]]+(-e|--eval)([[:space:]]|$)|ruby[[:space:]]+-e([[:space:]]|$)|php[[:space:]]+-r([[:space:]]|$)|find[[:space:]][^|;]*-delete' ; then
            suspicious=1
          else
            # Path-dependent mutation verbs; no verb -> read-only -> allow.
            # G6-synthesis P1: this verb list missed a whole family of commands
            # that write to disk — they returned read-only, which ALSO cleared
            # ATOM_FLOOR_MUTATION and so suppressed the opaque-mutation sentinel,
            # meaning the gate was never called at all for them.
            printf '%s' "$cmd_scan" | grep -qE '(^|[;&|`[:space:]])(mv|cp|rm|rmdir|truncate|tee|install|touch|mkdir|ln|chmod|chown|rsync|patch|unzip|tar|dd)[[:space:]]|sed[[:space:]]+-+i|(sed|awk|gawk)[[:space:]][^|;]*--?in-?place|gawk[[:space:]]+-[A-Za-z]*i[[:space:]]+inplace|git[[:space:]]+(add|mv|rm)([[:space:]]|$)|tar[[:space:]]+[^|;]*x|(curl|wget)[[:space:]]([^|;]*[[:space:]])?-(o|O)([[:space:]]|$)|dd[[:space:]][^|;]*of=|(go|cargo)[[:space:]]+build|npx[[:space:]]|python3?[[:space:]]+[^-][^[:space:]]*\.py|sqlite3[[:space:]]|>\||&>|[0-9]?>>?' || return 0
            # Path tokens from the SANITIZED stream (T18 codex P1 fold): a
            # whitelisted path inside quotes or a comment is DATA and must
            # never authorize an unrelated mutator (`rm x # holding/TODO.md`).
            # Quoted operand paths therefore don't authorize either — the
            # command just requires an open atom (stricter, never looser).
            local had_tokens=0
            ATOM_FLOOR_BASH_TARGETS=""
            # G5 deepseek P1: a QUOTED mutation target ('src/a;b') disappears in
            # the sanitize pass, so the envelope check never saw it. Recover
            # quoted single-token paths (no whitespace = not prose) from the RAW
            # command and hand them to the gate. Prose in quotes has spaces and
            # stays out — that is what keeps the FP rate at zero.
            local _af_q
            for _af_q in $(printf '%s' "$cmd_nohd" | grep -oE "'[^' ]*/[^' ]*'|\"[^\" ]*/[^\" ]*\"" | tr -d "'\"" | head -10); do
              # FP-replay #10: quoted URL fragments ('tps://api.example.') are
              # recovered as paths by the no-space rule. Any scheme separator
              # disqualifies a token from being a repo path.
              # FP-replay #12: a quoted JSON payload has no spaces and contains
              # '/', so the "single token with a slash" rule recovered it as a
              # path. Structured data is never a mutation target.
              case "$_af_q" in
                */dev/null*|*://*|http*|*'$'*) continue ;;
                *'{'*|*'}'*|*'['*|*']'*|*'":"'*|*':'*) continue ;;
                # FP-replay #14: printf FORMAT strings ('...%s\n') have no
                # spaces and contain '/', so the single-token rule recovered
                # them. A repo path never carries a backslash escape or '%'.
                *'\'*|*'%'*) continue ;;
              esac
              # FP-replay #16 (a-db25e6c4-07, amended per codex+deepseek
              # 2026-08-26): a token made ONLY of slashes and dots is jq/awk
              # string data ("/"), never a path. Digit-only paths (log/2024/07)
              # remain targets (digits are alnum).
              printf '%s' "$_af_q" | grep -qE '^[/.]+$' && continue
              # FP-replay #15 + #17 (a-db25e6c4-07): resolve the pipe-segment
              # carrying this quoted token. In sed/awk segments, pipe-bearing
              # tokens are EXPRESSIONS (s|a/b|c|g), never file operands. Pure
              # text-reader segments with no unquoted output redirect
              # contribute no targets. In-place editors (sed -i anywhere,
              # --in-place, gawk -i inplace) stay mutators (codex fold). The
              # redirect check runs on a quote-stripped copy so a '>' inside a
              # quoted awk program is not mistaken for a shell redirect.
              local _af_seg_line _af_seg_word _af_seg_noq _af_inplace
              local _af_nohd_split="$cmd_nohd"
              _af_nohd_split="${_af_nohd_split// | /$'\n'}"
              _af_nohd_split="${_af_nohd_split//||/$'\n'}"
              _af_nohd_split="${_af_nohd_split//&&/$'\n'}"
              _af_nohd_split="${_af_nohd_split//;/$'\n'}"
              _af_seg_line=$(printf '%s\n' "$_af_nohd_split" | grep -F -m1 -- "$_af_q" || true)
              if [ -n "$_af_seg_line" ]; then
                _af_seg_word=$(printf '%s\n' "$_af_seg_line" \
                  | sed -E 's/^[[:space:]]*//; s/^([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*//' \
                  | awk '{print $1}')
                _af_seg_word="${_af_seg_word##*/}"
                _af_seg_noq=$(printf '%s' "$_af_seg_line" | sed -E "s/'[^']*'//g; s/\"[^\"]*\"//g")
                _af_inplace=0
                printf '%s' "$_af_seg_line" | grep -qE '(^|[[:space:]])--?in-?place([[:space:]=]|$)|[[:space:]]-[A-Za-z]*i([[:space:]]|$)' && _af_inplace=1
                case "$_af_seg_word" in
                  sed|awk|gawk)
                    case "$_af_q" in *'|'*) continue ;; esac
                    if [ "$_af_inplace" = 0 ] && ! printf '%s' "$_af_seg_noq" | grep -q '>'; then continue; fi ;;
                  grep|egrep|fgrep|rg|jq|cut|tr|comm|diff|column|head|tail|sort|uniq|wc|test|\[)
                    printf '%s' "$_af_seg_noq" | grep -q '>' || continue ;;
                esac
              fi
              _atom_floor_whitelisted "$_af_q" && continue
              # Q: prefix = "already known to be a single quoted path" — the
              # dispatcher's prose-token filter must NOT re-judge these, or a
              # file literally named `a;b` slips past the envelope check.
              ATOM_FLOOR_BASH_TARGETS="${ATOM_FLOOR_BASH_TARGETS}${ATOM_FLOOR_BASH_TARGETS:+
}Q:$_af_q"
            done
            # G5 codex P1: slashless root-level targets (`>> README.md`,
            # `rm package.json`) never reached the envelope check. Token set =
            # slash-bearing tokens PLUS redirect targets PLUS dotted filenames.
            # FP-replay #9 (general form of #8): a segment that IS an exempt CLI
            # invocation contributes NO targets — its operands are the CLI's own
            # declarations (`sutra-atom open --touches X`), not mutations. The
            # CLI enforces its own discipline; gating its arguments deadlocks it.
            local _af_scan_targets
            _af_scan_targets=$(printf '%s\n' "$cmd_scan" | tr ';&|\n' '\n\n\n\n' \
              | grep -vE "$_af_exempt_re")
            for tok in $(printf '%s' "$_af_scan_targets" \
                  | sed -E 's/([0-9]?>>?)[[:space:]]*/\1/g' \
                  | tr ' ' '\n' \
                  | sed -E 's/^[0-9]?>>?//' \
                  | grep -E '/|^[A-Za-z0-9_.-]+\.[A-Za-z0-9]+$' | head -30); do
              # FP-replay #13: `FIX=holding/tests/...` is an ASSIGNMENT, not a
              # target. Strip a leading NAME= prefix and keep the value — that
              # value is often the real path the command writes to later.
              # (Cannot skip all '=' tokens: '=' is legal in a filename, G5.)
              case "$tok" in
                [A-Za-z_]*=*) tok="${tok#*=}"; [ -n "$tok" ] || continue ;;
              esac
              case "$tok" in */dev/null*|2\>*) continue ;; esac
              # FP-replay #8: an exempt CLI invoked by PATH (`holding/bin/sutra-atom
              # close ...`) is a command word, not a mutation target. Its own path
              # must never be gated — that made the CLIs unusable inside compounds.
              case "${tok##*/}" in
                sutra-atom|sutra-marker|sutra-dispatch|routing-policy-resolve|context-manifest|flow-ledger-append|wdp-evidence|rtk|dispatch-report.sh) continue ;;
              esac
              had_tokens=1
              # W6-T52: collect ALL non-whitelisted tokens (no break) — same
              # verdict, but the dispatch gate needs the full target list.
              if ! _atom_floor_whitelisted "$tok"; then
                suspicious=1
                ATOM_FLOOR_BASH_TARGETS="${ATOM_FLOOR_BASH_TARGETS}${ATOM_FLOOR_BASH_TARGETS:+
}$tok"
              fi
            done
            # All tokens whitelisted = known-safe mutation.
            [ "$suspicious" = "0" ] && [ "$had_tokens" = "1" ] && return 0
            # W1: ambiguous lane REMOVED — verb-matched command with no
            # authorizing tokens gates outright (net-stricter; the lane let
            # `rm x.txt 2>/dev/null` through via the /dev/null token).
            suspicious=1
          fi
          # A suspicious verdict IS the floor saying "this mutates". Export it
          # so the dispatch gate can demand a bound record even when no target
          # could be named (G6 codex/deepseek P1).
          [ "$suspicious" = "1" ] && ATOM_FLOOR_MUTATION=1
        fi
        ;;
      *) return 0 ;;
    esac

    open_atom=""
    if [ -d "$state" ]; then
      open_atom=$(grep -l '"status": *"open"' "$state"/a-*/atom.json 2>/dev/null | head -1 \
        | xargs -I{} sh -c 'basename "$(dirname "{}")"' 2>/dev/null || true)
    fi

    # W1-T17 interim d1 mitigation (SOFT): open atom exists but its declared
    # touches do not cover an Edit/Write target -> log touches_miss, ALLOW.
    # M1/M2 semantics per TOUCHES-CONTRACT: exact file, or dir-prefix with
    # '/' boundary. Feeds W6-T50 HARD-gate calibration; never blocks.
    if [ -n "$open_atom" ] && [ -n "$fpath" ] && { [ "$tool" = "Edit" ] || [ "$tool" = "Write" ]; }; then
      local rel="${fpath#"$root"/}" covered=0 t
      while IFS= read -r t; do
        [ -z "$t" ] && continue
        if [ "${t%/}" != "$t" ]; then
          case "$rel" in "${t%/}"/*) covered=1; break ;; esac
        else
          [ "$rel" = "$t" ] && { covered=1; break; }
        fi
      done < <(jq -r '.touches[]?' "$state/$open_atom/atom.json" 2>/dev/null)
      if [ "$covered" = "0" ]; then
        printf '{"ts":%s,"sid":"%s","tool":"%s","path":"%s","atom_id":"%s","event":"touches_miss","mode":"SOFT"}\n' \
          "$ts" "$sid" "$tool" "$rel" "$open_atom" >> "$root/.enforcement/atom-gate.jsonl" 2>/dev/null || true
      fi
    fi

    mkdir -p "$root/.enforcement/flow-journal" 2>/dev/null || return 0
    printf '{"ts":%s,"sid":"%s","tool":"%s","path":"%s","atom_id":"%s"}\n' \
      "$ts" "$sid" "$tool" "$target" "${open_atom:-none}" \
      >> "$root/.enforcement/flow-journal/$sid.jsonl" 2>/dev/null || true

    if [ -z "$open_atom" ]; then
      printf '{"ts":%s,"sid":"%s","tool":"%s","path":"%s","event":"would_block","mode":"%s"}\n' \
        "$ts" "$sid" "$tool" "$target" "$mode" \
        >> "$root/.enforcement/atom-gate.jsonl" 2>/dev/null || true
      ATOM_FLOOR_VERDICT="block"
    fi
  } 2>/dev/null
  return 0
}
