# npm, yarn and pnpm audit

Execution detail for `npm`, `yarn`, `pnpm`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

Precondition — determine which package manager applies:

- `package-lock.json` or `npm-shrinkwrap.json` present AND `which npm` succeeds → npm
- `yarn.lock` present (no npm lockfile) AND `which yarn` succeeds → yarn
- `pnpm-lock.yaml` present AND `which pnpm` succeeds → pnpm
- Lockfile present, binary absent → "Not available (lockfile found but binary missing)"
- No lockfile → "Not applicable (no lockfile)" and skip

```bash
npm_out=$(npm audit --json 2>"$_sa_tmp/npm-err.txt")
```

Parse `.vulnerabilities` (object keyed by package name) → `.severity`, `.via[]`, `.effects[]`, `.fixAvailable`. `.fixAvailable` may be `false`, `true`, or an object `{name, version, isSemVerMajor}` — when an object, use `.fixAvailable.version` as the fix version.

```bash
yarn_out=$(yarn audit --json 2>"$_sa_tmp/yarn-err.txt")
```

yarn outputs NDJSON — parse one JSON object per line, filter `.type == "auditAdvisory"`, read `.data.advisory.{severity, title, module_name, patched_versions, overview}`. Errored only if output is empty; non-zero exit with non-empty output is normal.

```bash
pnpm_out=$(pnpm audit --json 2>"$_sa_tmp/pnpm-err.txt")
```

Parse `.advisories` (object keyed by advisory ID) → `.severity`, `.title`, `.module_name`, `.patched_versions`, `.overview`.
