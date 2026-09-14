---
id: agent-loopholes-0c18e6b9
auditor: agent-loopholes
severity: high
category: security
area: scripts/hooks/_hooklib.py
status: open
found: 2026-09-13
location: scripts/hooks/_hooklib.py:62-71
location_sha: f4daa53d403f6fc2
---

# Hook tokenizer strips mid-word hashes and keeps backslash escapes, so guards judge the wrong command

## Problem

The shared tokenizer every shell guard uses treats `#` as a comment wherever it appears, while bash starts a comment only at the beginning of a word, and it leaves backslash escapes and `$'...'` quoting in the token text. The guard therefore judges a command the shell never runs.

## Evidence

```python
_COMMENT = re.compile(r"#[^\n]*")
_QUOTED = re.compile(r"'[^']*+'|\"(?:\\.|[^\"\\])*+\"")
```

Probes, JSON payload piped to the hook, exit codes observed in this audit:

- `git commit -m wip --no-verify` → 2 (control)
- `git commit -m issue#12 --no-verify` → 0
- `git commit -m wip \-\-no-verify` → 0
- `git push origin main` → 2 (control)
- `git push origin feat#1 main` → 0
The internal-tooling reviewer also observed exit 0 for `$'--no-verify'`, for `sed -i s/a/b/ x#y scripts/hooks/ruff-hook.py` against the agents-path hook (2 without the `x#y` token), and for `echo a#b; cat secret.txt # ctx-ok` against the ctx-ok guard (2 without `a#b`).

## Impact

The pre-commit bypass guard, the protected-branch push rule, write protection of the enforcement surface and the ctx-ok guard are each defeated by one ordinary-looking token such as an issue reference.

## Fix

In `_hooklib`: treat `#` as a comment only at the start of a word (start of line or after whitespace or `;&|()`); after unmasking quoted spans, pass each token through `shlex.split(token, posix=True)` to remove escapes; decode `$'...'`; deny any stage whose tokens still contain `\\` or `$'`. Add every shape above to `tests/test_hooks.py`. This file is owner-only enforcement surface.
