# snyk

Execution detail for `snyk`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

Snyk exits 0 (clean), 1 (vulnerabilities found OR unsupported project), or 2 (auth/network failure). Check for an `.error` field in the JSON before parsing — its presence means failure regardless of exit code.

```bash
snyk_out=$(snyk test --json 2>"$_sa_tmp/snyk-err.txt")
```

- exit 2 → "Errored: $(head -1 "$_sa_tmp/snyk-err.txt")" (common cause: `snyk auth` not run)
- exit 0/1 with `.error` field → "Errored: {.error value}"
- exit 0/1 without `.error` → parse normally

Output is a single object for single-project repos, a JSON array for monorepos — normalize by unioning `.vulnerabilities[]`. Each entry has `.id`, `.title`, `.severity`, `.packageName`, `.version`, `.description`, `.fixedIn`.
