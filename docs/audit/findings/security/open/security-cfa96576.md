---
id: security-cfa96576
auditor: security
severity: low
category: security
area: scripts/hooks/validate-rules-hook.py
status: open
found: 2026-10-04
location: scripts/hooks/validate-rules-hook.py:45-82
location_sha: e6a0863f99337ed3
---

# Hook payload path reaches validate-rules.py argv (CodeQL alert #4, py/command-line-injection)

## Problem

The PostToolUse payload's file path (read from stdin by `_hooklib.event_path`) flows into the `uv run validate-rules.py -- <candidate>` argv. CodeQL alert #4 (critical, open since 2026-08-31) reports it as py/command-line-injection under the `local` threat model. The realpath + startswith containment guard added to clear it does not, and its comment claims CodeQL recognises that form as a guard.

## Evidence

GitHub code-scanning alert #4 open on refs/heads/main at 2ff33c1, line 82. Reproduced locally with CodeQL 2.26.4 / python-queries 1.8.11, CWE-078/CommandInjection.ql, --threat-model=local: source _hooklib.py:299, sink validate-rules-hook.py:82.

## Impact

Not exploitable as shell injection (argv list, no shell, `--` terminator), but a critical alert stays open on a required-review surface, and the in-code comment states a guarantee that does not hold.

## Fix

Owner-only surface: patch `codeql-command-line-injection.patch` in the repo working directory. It passes every `*.md` listed from `.claude/rules/` instead of the payload path (which now only decides whether the hook runs), drops the incorrect CodeQL-guard comment, and adds `test_validate_rules_hook_argv_carries_the_rules_listing_not_the_payload_path`. A local CodeQL run on the patched tree no longer reports the hook. Resolve once the owner applies it.
