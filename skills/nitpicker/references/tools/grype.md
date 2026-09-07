# grype

Execution detail for `grype`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

Precondition: a supported manifest exists (`go.sum`, `package-lock.json`, `requirements.txt`, `Gemfile.lock`, `Cargo.lock`, `composer.lock`, `yarn.lock`, `pnpm-lock.yaml`). None found → record "Not applicable (no supported manifest)" and skip.

```bash
grype_out=$(grype dir:. --output json 2>"$_sa_tmp/grype-err.txt")
```

Parse `.matches[]` → `.vulnerability.id`, `.vulnerability.severity`, `.vulnerability.description`, `.artifact.name`, `.artifact.version`.
