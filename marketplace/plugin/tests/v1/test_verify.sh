#!/usr/bin/env bash
# W-BUILD-V1 S4-C2 acceptance: sutra-verify against REAL files (no mocks).
# Covers: pass/fail per template, pin miss, arg mapping errors, countersign, evidence line.
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
SV="$HERE/../../bin/sutra-verify"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

pass=0; fail=0
OUT=""; RC=0

run() { OUT="$("$@" 2>&1)"; RC=$?; }

t() { # t <name> <want_rc> [required-substring ...]
  local name="$1" want_rc="$2"; shift 2
  if [ "$RC" -ne "$want_rc" ]; then
    echo "FAIL $name (rc=$RC want=$want_rc)"; echo "$OUT" | sed 's/^/    /'
    fail=$((fail+1)); return
  fi
  local pat
  for pat in "$@"; do
    if ! printf '%s' "$OUT" | grep -qF -- "$pat"; then
      echo "FAIL $name (missing: $pat)"; echo "$OUT" | sed 's/^/    /'
      fail=$((fail+1)); return
    fi
  done
  echo "PASS $name"; pass=$((pass+1))
}

# --- real fixtures -----------------------------------------------------------
printf 'alpha\nbeta\nalpha\n' > "$TMP/data.txt"
printf 'second file\n'        > "$TMP/other.txt"
: > "$TMP/empty.txt"
printf 'echo "got:$1"\nexit 0\n' > "$TMP/ok.sh"
printf 'echo "boom" >&2\nexit 7\n' > "$TMP/bad.sh"

# --- file-exists@1 -----------------------------------------------------------
run "$SV" --template file-exists --version 1 --arg "path=$TMP/data.txt"
t t01-file-exists-pass 0 "OUTCOME: pass" "EVIDENCE: " '"template_id":"file-exists"' '"template_version":1' "present: $TMP/data.txt"

run "$SV" --template file-exists --version 1 --arg "path=$TMP/data.txt" --arg "path=$TMP/other.txt"
t t02-file-exists-repeat-arg 0 "OUTCOME: pass" "present: $TMP/data.txt" "present: $TMP/other.txt"

run "$SV" --template file-exists --version 1 --arg "path=$TMP/missing.txt"
t t03-file-exists-missing 1 "OUTCOME: fail-retry" "missing or empty"

run "$SV" --template file-exists --version 1 --arg "path=$TMP/empty.txt"
t t04-file-exists-empty 1 "OUTCOME: fail-retry" '"exit_code":1'

# --- grep-count@1 ------------------------------------------------------------
run "$SV" --template grep-count --version 1 --arg "pattern=alpha" --arg "file=$TMP/data.txt" --arg "min=2"
t t05-grep-count-pass 0 "OUTCOME: pass" "found 2 of >=2 required"

run "$SV" --template grep-count --version 1 --arg "pattern=alpha" --arg "file=$TMP/data.txt" --arg "min=3"
t t06-grep-count-under-min 1 "OUTCOME: fail-retry" "found 2 < 3"

run "$SV" --template grep-count --version 1 --arg "pattern=alpha" --arg "file=$TMP/data.txt" --arg "min=0"
t t07-grep-count-vacuous-min 1 "OUTCOME: fail-retry" "min=0 is vacuous"

# --- named-test@1 ------------------------------------------------------------
run "$SV" --template named-test --version 1 --arg "script=$TMP/ok.sh" --arg "arg=hello"
t t08-named-test-pass-arg-passthrough 0 "OUTCOME: pass" "got:hello"

run "$SV" --template named-test --version 1 --arg "script=$TMP/bad.sh"
t t09-named-test-fail-code-passthrough 1 "OUTCOME: fail-retry" '"exit_code":7' "boom"

# --- pinning -----------------------------------------------------------------
run "$SV" --template file-exists --version 99
t t10-pin-miss-version 4 "no pinned template file-exists@99"

run "$SV" --template no-such-template --version 1
t t11-pin-miss-id 4 "no pinned template no-such-template@1"

# --- arg mapping errors ------------------------------------------------------
run "$SV" --template grep-count --version 1 --arg "pattern=alpha" --arg "file=$TMP/data.txt"
t t12-missing-required-arg 2 "missing required arg" "min"

run "$SV" --template grep-count --version 1 --arg "pattern=a" --arg "file=$TMP/data.txt" --arg "min=1" --arg "bogus=x"
t t13-unknown-arg-name 2 "unknown arg name"

run "$SV" --template grep-count --version 1 --arg "pattern=a" --arg "pattern=b" --arg "file=$TMP/data.txt" --arg "min=1"
t t14-non-repeat-arg-duplicated 2 "more than once"

# --- countersign (record-only in v1) -----------------------------------------
run "$SV" --template file-exists --version 1 --arg "path=$TMP/data.txt" --countersign sankalpasawa
t t15-countersign-note 0 "OUTCOME: pass" "COUNTERSIGN: " '"operator":"sankalpasawa"' "record-only (v1)"

run "$SV" --template file-exists --version 1 --arg "path=$TMP/data.txt"
if printf '%s' "$OUT" | grep -qF -- "COUNTERSIGN"; then
  echo "FAIL t16-no-countersign-without-flag"; fail=$((fail+1))
else
  echo "PASS t16-no-countersign-without-flag"; pass=$((pass+1))
fi

# --- evidence line is one parseable JSON row ---------------------------------
run "$SV" --template grep-count --version 1 --arg "pattern=alpha" --arg "file=$TMP/data.txt" --arg "min=1"
EV_LINE="$(printf '%s\n' "$OUT" | grep '^EVIDENCE: ' | sed 's/^EVIDENCE: //')"
if printf '%s' "$EV_LINE" | python3 -c 'import json,sys; r=json.load(sys.stdin); assert r["verify_template"]=={"template_id":"grep-count","template_version":1}; assert r["verify_args"][0]=={"name":"pattern","value":"alpha"}; assert r["outcome"]=="pass"; assert len(r["script_sha256"])==64'; then
  echo "PASS t17-evidence-json-shape"; pass=$((pass+1))
else
  echo "FAIL t17-evidence-json-shape"; echo "$EV_LINE" | sed 's/^/    /'; fail=$((fail+1))
fi

echo "RESULT: pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
