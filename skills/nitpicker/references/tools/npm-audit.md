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

yarn's audit command depends on its major version, so read `yarn --version` first. Both forms print NDJSON: parse one JSON object per line. For either form, record Errored when the output is empty or contains no parseable JSON line — a `Usage Error` message is non-empty and parses as nothing. Non-zero exit with parseable lines is normal.

Yarn 1.x:

```bash
yarn_out=$(yarn audit --json 2>"$_sa_tmp/yarn-err.txt")
```

Filter `.type == "auditAdvisory"`, read `.data.advisory.{severity, title, module_name, patched_versions, overview}`.

Yarn 2 and later have no `audit` command — `yarn audit` exits 1 with `Usage Error: Couldn't find a script named "audit".` Run:

```bash
yarn_out=$(yarn npm audit --json --recursive 2>"$_sa_tmp/yarn-err.txt")
```

`--recursive` includes transitive dependencies; without it only direct ones are audited. In Yarn 4, each advisory is one line shaped `{"value": <package>, "children": {"ID", "Issue", "URL", "Severity", "Vulnerable Versions", "Tree Versions", "Dependents"}}` — read `.value` as the package, `.children.Issue` as the title, `.children.Severity`, `.children["Vulnerable Versions"]`, and `.children["Tree Versions"]` as the installed versions. An `ID` ending in ` (deprecation)` is a deprecated package, not a vulnerability. The command exits 1 when it prints advisories. A clean run exits 0 and prints a single `.type == "info"` line whose `.data` is `No audit suggestions`. Output whose lines match neither shape (Yarn 2 and 3 are not covered here) is Errored with its first line, never parsed as clean.

```bash
pnpm_out=$(pnpm audit --json 2>"$_sa_tmp/pnpm-err.txt")
```

Parse `.advisories` (object keyed by advisory ID) → `.severity`, `.title`, `.module_name`, `.patched_versions`, `.overview`.
