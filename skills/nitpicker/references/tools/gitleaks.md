# gitleaks

Execution detail for `gitleaks`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

```bash
gitleaks_out=$(gitleaks detect --source . --report-format json --exit-code 0 2>"$_sa_tmp/gitleaks-err.txt")
```

With `--exit-code 0`, non-zero exit always means a genuine crash, not "found secrets". gitleaks outputs `null` (not `[]`) when no secrets are found — `null` is valid JSON, treat it as an empty findings array, never as an error. Otherwise parse `.[].RuleID`, `.[].Description`, `.[].File`, `.[].StartLine`, `.[].Commit`, `.[].Secret` (redact the secret value per the evidence-redaction rule in `_conventions.md`).
