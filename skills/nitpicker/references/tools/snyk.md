# snyk

Execution detail for `snyk`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

Snyk exits 0 (clean), 1 (vulnerabilities found), 2 (failure — auth, network, or a project it failed to scan), or 3 (no supported project detected). Check for an `.error` field in the JSON before parsing — outside exit 3, its presence means failure regardless of exit code.

```bash
snyk_out=$(snyk test --json 2>"$_sa_tmp/snyk-err.txt")
```

- exit 3 → "Not applicable (no supported target files)" — its output carries an `.error` naming the missing target files; this is the one `.error` that is not Errored
- exit 2 → "Errored: $(head -1 "$_sa_tmp/snyk-err.txt")" (common cause: `snyk auth` not run)
- any other exit with an `.error` field → "Errored: {.error value}"
- exit 0/1 without `.error` → parse normally

Output is a single object for single-project repos, a JSON array for monorepos — normalize by unioning `.vulnerabilities[]`. Each entry has `.id`, `.title`, `.severity`, `.packageName`, `.version`, `.description`, `.fixedIn`.
