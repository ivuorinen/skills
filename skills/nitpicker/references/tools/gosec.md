# gosec

Execution detail for `gosec`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

Precondition: Go source exists (`find . -name "*.go" -not -path "*/vendor/*" | head -1`). None → record "Not applicable (no Go source files)" and skip.

```bash
gosec_out=$(gosec -fmt json ./... 2>"$_sa_tmp/gosec-err.txt")
```

Parse `.issues[]` → `.rule_id`, `.details`, `.severity`, `.confidence`, `.file`, `.line`.
