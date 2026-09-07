# semgrep and opengrep

Execution detail for `semgrep`, `opengrep`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

**Run the binary detection actually found.** The two are CLI-compatible for this
invocation, and a host commonly has one and not the other — so the command is
parameterised rather than hardcoding `semgrep`. Hardcoding it means a host with
only `opengrep` runs a binary that is not installed, and the run records
"Errored" for a scanner that was available all along.

```bash
# $_sa_semgrep is whichever of the two the preflight found. Prefer `opengrep`
# where both exist: it parses `match` statements, which semgrep 1.172.0 cannot —
# semgrep drops the whole file on one, so a repo using them is silently
# under-scanned rather than reported as failed.
_sa_semgrep=$(command -v opengrep || command -v semgrep)

semgrep_out=$("$_sa_semgrep" --json --config=auto --quiet . \
  2>"$_sa_tmp/semgrep-err.txt")
```

Parse `.results[]` → `.check_id`, `.path`, `.start.line`, `.extra.severity`, `.extra.message`.

Record which binary ran in the run summary. "semgrep: clean" and "opengrep:
clean" are different claims — the two ship different rule sets, and `p/python`
omits the `-audit` rule variants that `r/python.lang.security.audit` carries.
