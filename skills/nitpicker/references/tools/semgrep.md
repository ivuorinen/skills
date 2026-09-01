# semgrep and opengrep

Execution detail for `semgrep`, `opengrep`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

```bash
semgrep_out=$(semgrep --json --config=auto --quiet . 2>"$_sa_tmp/semgrep-err.txt")
```

Parse `.results[]` → `.check_id`, `.path`, `.start.line`, `.extra.severity`, `.extra.message`.
