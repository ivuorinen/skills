# codeql

Execution detail for `codeql`, read by `/nitpicker security` after detection finds the binary. The shared capture protocol, the temp-directory handling and the error-recording rules live in `commands/security.md` and bind here too.

Two phases rather than one command: a database is built from source, then
queries run against it. Budget minutes per language, so this is not a cheap
probe like the others — run it when the depth is wanted, and record it as
"Not run (cost)" rather than pretending it was unavailable.

Precondition: `codeql` on PATH. Detect the languages present and build one
database each. A language with no database yields no findings and is recorded
as **uncovered**, never as clean — the distinction the whole preflight rule
exists for.

```bash
codeql database create "$_sa_tmp/db-$lang" --language="$lang" \
  --source-root=. --overwrite 2>"$_sa_tmp/codeql-db-$lang-err.txt"

codeql database analyze "$_sa_tmp/db-$lang" \
  --format=sarif-latest --output="$_sa_tmp/codeql-$lang.sarif" --download \
  "codeql/$lang-queries:codeql-suites/$lang-security-and-quality.qls" \
  2>"$_sa_tmp/codeql-$lang-err.txt"
```

**Name the suite explicitly.** Dropping the trailing
`codeql/<lang>-queries:codeql-suites/<lang>-security-and-quality.qls` argument
runs the pack's default suite, which is security-only: on a Python tree that is
43 rules where `security-and-quality` carries 172. The shorter run reports clean
over a quarter of the rules and is indistinguishable from a clean run over all
of them, because the quality queries are not merely passing — they never
execute. `py/mixed-returns`, `py/empty-except` and `py/import-and-import-from`
are absent from the default suite entirely.

Output is SARIF, so it goes through the consolidation below rather than needing
its own parser. A completed analysis exits 0 whether or not it found anything;
a non-zero exit means the database build or the query run failed, which is
"Errored", not "clean".

Judge the run by that exit status and by `meta.errors` after consolidation,
never by whether a SARIF file is present. Wrappers commonly delete a
zero-result file, and a wrapper that counts results with `jq` also reports zero
when `jq` fails to parse — so a missing file means "no findings" and "the run
broke" equally.
