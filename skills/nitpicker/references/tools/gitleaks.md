# gitleaks

Execution detail for `gitleaks`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

```bash
gitleaks_out=$(gitleaks detect --source . --report-format json --report-path - --exit-code 0 2>"$_sa_tmp/gitleaks-err.txt")
```

`--report-path -` is what sends the JSON report to stdout; without it gitleaks prints nothing there, and the empty capture is recorded as Errored. With `--exit-code 0`, non-zero exit always means a genuine crash, not "found secrets". A clean run prints `[]`. Otherwise parse `.[].RuleID`, `.[].Description`, `.[].File`, `.[].StartLine`, `.[].Commit`, `.[].Secret` (redact the secret value per the evidence-redaction rule in `_conventions.md`).
