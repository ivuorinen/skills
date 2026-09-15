---
paths:
  - "package.json"
  - "pyproject.toml"
  - "uv.lock"
  - ".claude-plugin/**"
  - ".release-please-manifest.json"
  - "scripts/bump-version.py"
  - "scripts/check-version-sync.py"
  - ".github/workflows/release-please.yml"
---

# Version Bumps

Use `scripts/bump-version.py` for manual bumps; release-please handles it on CI.

`uv.lock` carries one more copy in its root `[[package]]` entry.
Neither `check-version-sync.py` nor release-please covers it — 3.0.0 shipped
with the lockfile still declaring 2.0.0. `make lock-check` gates it with
`uv lock --check`, uv's own staleness test, which also catches dependency drift.

Both bump paths keep it current. `bump-version.py` re-locks after writing the
manifests. On CI, the `sync-lockfile` job in `release-please.yml` commits the
regenerated lockfile onto the release PR, because release-please has no updater
for it.

Re-locking is best-effort rather than guaranteed. When `uv` is absent, times
out, or fails, `bump-version.py` reports the failure and continues instead of
aborting a bump whose manifests are already written. It names the recovery in
its output.

Run `uv lock` to resync — that is the supported way to move the version in the
lockfile. Hand-edit `uv.lock` only where uv cannot run at all, and treat that as
a stopgap: the next `uv lock` overwrites the value.

## Enforcement

The values are gated: `make version-sync` fails on manifests that disagree, and
`make lock-check` on a stale `uv.lock`. Which route moved them — the script, CI,
or a hand edit — is author discipline.
