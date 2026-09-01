# trivy

Execution detail for `trivy`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

```bash
trivy_out=$(trivy fs . --format json --quiet 2>"$_sa_tmp/trivy-err.txt")
```

Parse `.Results[].Vulnerabilities[]` → `.VulnerabilityID`, `.Severity`, `.Title`, `.PkgName`, `.InstalledVersion`, `.FixedVersion`. Also parse `.Results[].Misconfigurations[]` (IaC) and `.Results[].Secrets[]`.
