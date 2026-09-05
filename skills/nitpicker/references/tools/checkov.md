# checkov

Execution detail for `checkov`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

```bash
checkov_out=$(checkov -d . --output json --quiet 2>"$_sa_tmp/checkov-err.txt")
```

Output may be a JSON object (single framework) or a JSON array (multiple). Normalize: array → collect `.results.failed_checks[]` from each element; object → use `.results.failed_checks[]` directly. Each failed check has `.check_id`, `.check_result.result`, `.resource`, `.file_path`, `.file_line_range`, `.check.name`.
