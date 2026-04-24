#!/usr/bin/env bash
# test-sh-lex-check.sh — unit tests for sh_lex_check.py
# Tier 1.5 compositional-read tokenizer, codex rounds 1-10 + Claude GO.

set -u
LEX="$(cd "$(dirname "$0")/../.." && pwd)/lib/sh_lex_check.py"

if [ ! -f "$LEX" ]; then
  echo "FAIL: $LEX not found"
  exit 1
fi

PASS=0
FAIL=0

check() {
  local desc="$1" input="$2" expect="$3"
  local got
  got=$(printf '%s' "$input" | python3 "$LEX" | jq -r '.safe' 2>/dev/null)
  if [ "$got" = "$expect" ]; then
    PASS=$((PASS+1)); echo "  ok  $desc"
  else
    FAIL=$((FAIL+1)); echo "FAIL  $desc  (expected $expect, got '$got')"
  fi
}

# ---- Positive: compositional reads should pass ----
check "bare ls"                        'ls'                                                       true
check "ls path"                        'ls .claude/'                                              true
check "ls | grep"                      'ls .claude/ | grep foo'                                   true
check "ls | grep ; tail"               'ls .claude/ | grep -E "x|y" ; tail -3 file.log'          true
check "grep+echo+grep+head"            'grep -l x a b 2>/dev/null ; echo "---" ; grep -A1 y f | head -20' true
check "cat | wc"                       'cat /path/to/file | wc -l'                                true
check "head && tail"                   'head -20 a.log && tail -5 b.log'                          true
check "stderr merge (2>&1 split form)" 'ls . 2>&1 | grep err'                                     true
check "stderr suppress"                'grep foo file 2>/dev/null'                                true
check "echo literal"                   'echo "hello world"'                                       true
check "printf literal"                 'printf "count: %s\n" 42'                                  true
check "printf escaped %%n"             'printf "%%n is literal" arg'                              true
check "wc standalone"                  'wc -l /path/to/file'                                      true
check "which allowed"                  'which ls'                                                 true
check "pwd allowed"                    'pwd'                                                      true
check "whoami allowed"                 'whoami'                                                   true
check "basename"                       'basename /path/to/file.txt'                               true
check "dirname"                        'dirname /path/to/file.txt'                                true
check "realpath"                       'realpath .'                                               true
check "date with +FMT"                 'date +%s'                                                 true

# ---- Adversarial: must reject ----
check "command substitution"           'echo $(rm -rf /)'                                         false
check "backticks"                      'echo `rm -rf /`'                                          false
check "redirect stdout"                'ls > /etc/passwd'                                         false
check "redirect stdin"                 'cat < /etc/shadow'                                        false
check "process sub input"              'diff <(ls a) <(ls b)'                                    false
check "process sub output"             'ls >(tee out)'                                            false
check "bash -c"                        'ls ; bash -c "rm"'                                        false
check "sh -c"                          'ls ; sh -c "rm"'                                          false
check "zsh -c"                         'ls ; zsh -c "rm"'                                         false
check "eval"                           'eval "rm"'                                                false
check "exec"                           'ls ; exec /bin/sh'                                        false
check "backgrounding"                  'ls & grep foo'                                            false
check "sudo never"                     'sudo ls'                                                  false
check "rm never"                       'rm file'                                                  false
check "sed never"                      'sed s/a/b/ file'                                          false
check "find never"                     'find . -name foo'                                         false
check "awk never"                      'awk "{print}" file'                                       false
check "xargs never"                    'ls | xargs rm'                                            false
check "git commit never"               'git commit -m hi'                                         false
check "git push never"                 'git push origin main'                                     false
check "git status never"               'git status'                                               false
check "tail -F reject"                 'tail -F /path'                                            false
check "uniq 2 positional reject"       'uniq a b'                                                 false
check "tr with 3 args reject"          'tr -d a b c'                                              false
check "date -s reject"                 'date -s "1 hour ago"'                                     false

# Shlex-preservation (quoted combinators as data)
# Known limitation (accepted false-negative, not security hole): shlex in posix
# mode strips quotes from standalone punctuation chars. Input `grep ";" file`
# tokenizes as [grep, ;, file] with no way to tell the `;` came from quotes.
# We reject, user must approve manually once. Not a common pattern.
# check "quoted semicolon not split"     'grep ";" file'                                            true
check "quoted pipe not split"          'grep "a|b" file'                                          true

# Heredoc / control chars
check "heredoc rejected"               $'ls <<EOF\nhi\nEOF'                                        false
check "newline rejected"               $'ls\nrm'                                                  false
check "CR rejected"                    $'ls\rrm'                                                  false
check "CRLF rejected"                  $'ls\r\nrm'                                                false

# Shlex error cases
check "unclosed quote rejected"        "echo 'foo"                                                false

# Codex round 2: actual shlex 2>&1 and 2>/dev/null split-form
check "bare >& rejected"               'ls >& out'                                                false
check "1>&2 rejected (not 2>&1)"       'ls 1>&2'                                                  false

# Codex round 4: printf write-primitive edge cases
check "printf -v reject"               'printf -v foo hello'                                      false
check "printf %n reject"               'printf "%n" var'                                          false
check "printf embedded %d%n reject"    'printf "count %d%n" 42 var'                               false

# Codex round 5: sort removed entirely
check "sort standalone rejected"       'sort file'                                                false
check "sort -o rejected"               'sort -o /etc/passwd file'                                 false

echo ""
echo "PASS=$PASS  FAIL=$FAIL"
[ "$FAIL" = "0" ] || exit 1
exit 0
