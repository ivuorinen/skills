# Findings Store Protocol — load before the first store operation of a run

Trigger: about to list, file, resolve, index, validate, baseline or migrate a
finding. `_conventions.md` holds the parts that bind before that point — the
finding contract, the redaction rule, the legacy-migration consent gate and the
run protocol — because a rule that only arrives with this file would not exist
in a run that never reaches it.

## Where findings live

Open findings live one file each under `docs/audit/findings/<auditor>/open/`
in the audited repository, where `<auditor>` is the command name; resolving a
finding appends a record to the append-only `docs/audit/findings/resolved.jsonl`
ledger and deletes the open file, so the tree never accumulates resolved files
and PR review stays readable.

## Two interfaces

Per the tool preference in `_conventions.md`, the MCP tools are the default and
the CLI is the fallback:

1. **The `nitpicker` MCP tools — the default whenever the session exposes
   them.** They call the same functions the CLI does, so the result is identical.
   The index is the one operation split across two tools rather than one:
   `np_findings_index` *renders* `INDEX.md` and returns it without writing,
   because it is annotated `readOnlyHint: true` and a read-only tool must not
   mutate the working tree; `np_write_index` writes it, and is the tool matching
   `findings.py index`. Pick by whether the file on disk should change. The tools
   otherwise need no shell, no path resolution, and no heredoc quoting, and
   the server enforces each tool's required parameters before dispatch (value
   checks stay in the backing functions, exactly as for the CLI). Use them for
   every operation in the table below; in a session that has them, dropping to
   the CLI for an operation a tool covers is a last resort, not a convenience.
2. **`scripts/findings.py` — the fallback.** The MCP server is Claude-native; in
   Copilot, pi, CI, or any session without the server, the CLI is the only
   interface and is fully sufficient. Never treat an absent MCP tool as a reason
   to skip filing a finding.

**After editing anything under `skills/*/scripts/`, switch to the CLI for the
rest of the session.** The server imports those modules once at startup and
holds them in memory, so a fix does not reach the running process — the `np_*`
tools keep executing the previous code, and the plugin-scope server serves the
*installed* copy, which never reflects a working-tree edit at any age. The CLI
loads fresh on every invocation. The mutate tools now prefix a `[warn]` line
when they detect either condition, but the warning is a backstop: an audit that
fixes a shipped tool and then resolves its own finding through the MCP tools
records "fixed" via the code path it just fixed and is not running.

| Operation | MCP tool | CLI equivalent |
| --- | --- | --- |
| File a finding | `np_new_finding` | `findings.py new` |
| Resolve a finding | `np_resolve_finding` | `findings.py resolve` |
| List findings | `np_list_findings` | `findings.py list` |
| List, waiving baselined ids | `np_list_findings` with `exclude_baseline: true` | `findings.py list --exclude-baseline` |
| Show one finding | `np_show_finding` | `findings.py show` |
| Validate the store | `np_validate_store` | `findings.py validate` |
| Render `INDEX.md` content (does **not** write) | `np_findings_index` | — |
| Write `INDEX.md` to disk | `np_write_index` | `findings.py index` |
| Export for another tool | — | `findings.py export --format sarif\|json\|junit` |
| Re-fingerprint recorded locations | — | `findings.py recheck` |

These operations have **no** MCP tool and always use the CLI: `baseline`,
`migrate`, `migrate-resolved`, `export`, and `recheck`. The first three omissions are
deliberate, not a gap waiting to be filled: `baseline` waives every open finding
from the release gate, and migration sits behind a per-run consent gate that
overrides autonomous mode (Run protocol step 0). The MCP mutate tools run with
no consent prompt, so shipping either as a tool would put a waiver or an
unconsented migration one call away. `export` is CLI-only for the opposite
reason — its output is a file for another system to ingest, so it belongs in a
shell pipeline, not in the model context. `recheck` is the same: it is a bulk
screen whose whole purpose is to keep findings *out* of the context window.
The mutate tools omit `--force`,
`--found`, and `--date` for the same reason as the first three — re-opening a
resolved finding, overwriting an existing one, or back-dating a record is a
CLI-only escape hatch, not something a tool call should reach by accident.

## CLI form

The CLI is stdlib-only, plain `python3`, no uv required. Resolve its path
relative to this skill's directory (Claude Code:
`${CLAUDE_SKILL_DIR}/scripts/findings.py`; below it is abbreviated
`findings.py`):

```bash
python3 findings.py new --auditor <command> --severity high \
  --category security --area src/auth.py --body - "Short title" <<'EOF'
## Problem
...
## Evidence
...
## Impact
...
## Fix
...
EOF
python3 findings.py resolve <id> --status fixed --notes "what changed"
python3 findings.py list --status open
python3 findings.py validate
python3 findings.py index
python3 findings.py export --format sarif > nitpicker.sarif
python3 findings.py recheck
```

## Provenance

`new` takes an optional `--location path:LINE` or `path:START-END`
(`np_new_finding`: `location`) naming where the evidence was read. Pass it
whenever the location is known. The tool stores it with a fingerprint of the
source there, and `recheck` re-computes every one in a single pass so `reverify`
can skip a finding whose cited bytes have not moved instead of spending a model
pass re-deriving the same conclusion.

`location` is the coordinate; the `## Evidence` body section is the prose. They
are separate fields on purpose. The location is not part of the content-hashed
id — folding a line range into the id would rehash the same defect after an
unrelated edit above it.

A location that cannot be fingerprinted — a directory, a subsystem name, a file
that moved — is stored without one and reported by `recheck` as
`unfingerprinted`. Provenance is an optimization; it never blocks filing.

## Index refresh

`INDEX.md` is refreshed for you when findings are filed or resolved through
`np_new_finding` / `np_resolve_finding` / the CLI — each writes the index
itself. Refresh it explicitly (`np_write_index`, else `findings.py index`)
only after changing the store some other way (a hand-edited or repaired
finding file). `np_findings_index` renders the content and does not write, so
it never refreshes anything.

## Export

`findings.py export` generates an interchange format from the store; the
markdown files stay canonical. `sarif` for a code-scanning interface, `json`
for another agent framework, `junit` for CI reporting. Export writes to stdout
and never mutates the store, so it is safe to run at any point.
