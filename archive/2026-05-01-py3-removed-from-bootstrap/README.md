# Archive — _sutra_project_lib.py (retired 2026-05-01, plugin v2.13.0)

## Why archived

`_sutra_project_lib.py` was the file-form Python helper introduced in plugin
v2.8.11 to dodge SIGKILL of stdin-fed `python3 - <<'PY'` heredocs from macOS
sandbox/EDR agents (vinit#38).

That fix solved one class of failure but not all. On 2026-05-01 user
@abhishekshah reported that `python3 -c "print('hello')"` itself exits 137
on his machine — the python3 binary is killed regardless of how it's invoked
(quarantine xattr, AV process-name killer, codesign mismatch). File-form vs
heredoc is irrelevant when python3 itself can't survive exec.

## Replacement

v2.13.0 ships `marketplace/plugin/scripts/_sutra_project_lib.sh` — a bash/jq
port with identical subcommands (`patch-profile`, `write-onboard`,
`stamp-identity`, `banner`) and the same atomic-write contract (mktemp + mv
inside the same directory; `rename(2)` is atomic on the same filesystem).

`scripts/start.sh` adds an upfront jq health gate so a missing-jq client gets
an actionable install hint rather than a silent half-bootstrap.

## Why kept (not deleted)

Per founder direction "archive, never delete" — this file is preserved here
in case any external caller depended on its CLI surface, and so the SIGKILL
research story stays browsable from the repo.

## Lineage

| Version | Status | Note |
|---|---|---|
| pre-v2.8.11 | inline `python3 - <<'PY'` heredocs in start.sh + onboard.sh | original form |
| v2.8.11 (2026-04-28) | extracted to this `.py` file (file form) | dodged heredoc-class SIGKILL |
| v2.13.0 (2026-05-01) | replaced by `_sutra_project_lib.sh` (bash/jq) | this file moved here |
