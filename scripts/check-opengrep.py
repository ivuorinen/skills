#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = "==3.11.*"
# ///
"""Run opengrep over the tools, and prove every `# nosemgrep` still earns its place.

Codacy runs opengrep on every pull request, but its engine configuration lives in
the Codacy UI and is invisible from a checkout. That gap is what this gate closes:
the findings Codacy reports become reproducible locally, from the repository alone.

Two checks, one scanner, run twice:

1. **Unsuppressed findings.** A finding opengrep reports with suppression active
   fails the gate. This is the half Codacy already performs; running it here moves
   the signal from post-push to pre-commit.
2. **Stale suppressions.** A second pass with `--disable-nosem` reveals every
   finding, including suppressed ones. A `# nosemgrep` marker lining up with no
   revealed finding is suppressing nothing, and fails the gate.

Check 2 is the one no external service performs, and it catches both halves of a
failure mode that is otherwise invisible. A marker written one line too far from
its call silently stops suppressing — opengrep honours a marker only on the
finding's own line or the line directly above it — and a marker left behind after
its call was rewritten silently keeps suppressing nothing. Neither shows up as a
diff, a warning, or a failing test; the first resurfaces a finding nobody expected,
the second hides a rule everyone assumed was live.

Scan errors are fatal. opengrep skips a file it cannot parse, so a parse error
means unscanned code, which must never read as "clean". Not theoretical: semgrep
1.172.0, the upstream, cannot parse a `match` statement and drops the whole file.
That is one reason this gate runs opengrep rather than semgrep.

Limitations, both flowing from the single configured ruleset:

* Staleness is judged only against `CONFIG`. A marker naming a rule outside that
  namespace has no finding to line up with and reads as stale, so suppressing a
  rule this gate does not run means widening the namespace first.
* Markers outside `SCAN_ROOTS` are judged neither way. Their count is printed
  rather than passed over silently, since an unjudged marker is exactly the thing
  this check exists to notice.

`CONFIG` names a registry namespace, which is mutable — the binary is pinned but
its rules are not, so a green run today can go red next month with no code
change. That is deliberate. Codacy runs a mutable ruleset too, and pinning ours
would make the two drift apart, which defeats the point of reproducing what
Codacy reports. Drift is loud in both directions rather than silent: a new rule
surfaces as an unsuppressed finding, and a withdrawn one turns every marker that
depended on it stale (measured — narrowing CONFIG to drop
`dangerous-subprocess-use-audit` fails the gate with seven stale markers, it does
not quietly pass). Vendor the corpus only if reproducing an old commit's verdict
ever matters more than tracking Codacy.

Exit codes: 0 success, 1 a finding or a stale marker (or an unrunnable scan under
CI), 2 usage error.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# The registry namespace that reproduces what Codacy reports here. `p/python`
# was measured and returns nothing on this repository — it omits the `-audit`
# rule variants, which are precisely the ones Codacy flags. Registry rules are
# fetched once and then cached by opengrep, so later runs need no network.
CONFIG = "r/python.lang.security.audit"

# Mirrors [tool.bandit] in pyproject.toml and the `opengrep` block in
# .codacy.yml: shipped tools plus internal tooling, tests excluded. opengrep
# skips tests/ through its own .semgrepignore regardless, so widening this
# without addressing that too would scan less than it appears to.
SCAN_ROOTS = ("skills", "scripts")

TIMEOUT = 600

# `nosem` is opengrep's other accepted spelling of the same marker.
_MARKER = re.compile(r"#\s*nosem(?:grep)?\b")

_SKIP_DIRS = {".venv", "graphify-out", "_extra", ".git", "__pycache__"}

USAGE = f"""usage: check-opengrep.py [--help]

Runs opengrep over {"/".join(SCAN_ROOTS)} and fails on either an unsuppressed
finding or a `# nosemgrep` marker that suppresses nothing.

Ruleset: {CONFIG}

Requires `opengrep` on PATH. Absent, this exits 0 with a notice — except under
CI, where a gate that cannot run is a failure rather than a pass.

Exit codes: 0 success, 1 finding or stale marker, 2 usage error.
"""


def _scan(opengrep: str, *, disable_nosem: bool) -> dict:
    """One opengrep pass over SCAN_ROOTS, as parsed JSON.

    Raises RuntimeError with a diagnosable message on anything leaving the result
    untrustworthy — a crash, a timeout, or unparseable output.
    """
    try:
        # argv is assembled here from module constants and a fixed flag list; the
        # single interpolated value is the opengrep path shutil.which resolved.
        # The marker must sit on the line directly above the call — opengrep
        # ignores it even one line further up, silently.
        # nosemgrep: dangerous-subprocess-use-audit
        result = subprocess.run(
            [
                opengrep,
                "scan",
                "--quiet",
                "--json",
                "--config",
                CONFIG,
                *(["--disable-nosem"] if disable_nosem else []),
                *SCAN_ROOTS,
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"opengrep exceeded {TIMEOUT}s") from None
    except OSError as exc:
        raise RuntimeError(f"could not run opengrep: {exc}") from None

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:800]
        raise RuntimeError(f"opengrep exited {result.returncode}\n{detail}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"opengrep did not emit JSON: {exc}") from None


def _locations(scan: dict) -> set[tuple[str, int]]:
    return {(r["path"], r["start"]["line"]) for r in scan.get("results", [])}


def _markers_in(paths: list[Path]) -> list[tuple[str, int, str]]:
    """Every marker in `paths`, as (repo-relative path, line number, source line).

    Tokenized rather than grepped. A textual search also matches the marker
    spelled inside a docstring or a string literal — this file alone contains
    four such mentions, every one of which a regex reported as a stale
    suppression. Only a real COMMENT token can suppress anything.
    """
    found = []
    for path in paths:
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            with path.open("rb") as handle:
                for token in tokenize.tokenize(handle.readline):
                    if token.type == tokenize.COMMENT and _MARKER.search(token.string):
                        found.append((rel, token.start[0], token.line.strip()))
        except (tokenize.TokenError, SyntaxError, UnicodeDecodeError) as exc:
            # Unreadable here means unscannable by opengrep too, so this is a
            # failure rather than a file to pass over.
            raise RuntimeError(f"could not tokenize {rel}: {exc}") from None
    return found


def _scanned_sources() -> list[Path]:
    return sorted(p for root in SCAN_ROOTS for p in (REPO_ROOT / root).rglob("*.py"))


def _unscanned_sources() -> list[Path]:
    roots = {REPO_ROOT / r for r in SCAN_ROOTS}
    return sorted(
        p
        for p in REPO_ROOT.rglob("*.py")
        if not any(root in p.parents for root in roots) and not _SKIP_DIRS.intersection(p.parts)
    )


def _report_errors(scans: list[dict]) -> int:
    """Scan errors mean unscanned files, so they are fatal rather than noted."""
    errors = [e for scan in scans for e in scan.get("errors", [])]
    if not errors:
        return 0
    print("opengrep could not scan every file, so this is not a clean bill:")
    for err in errors:
        message = (err.get("message") or err.get("type") or "").splitlines()
        print(f"  {err.get('path') or '(no path)'}: {message[0][:160] if message else ''}")
    return len(errors)


def _report_findings(active: dict) -> int:
    findings = sorted(active.get("results", []), key=lambda r: (r["path"], r["start"]["line"]))
    if not findings:
        return 0
    print("Unsuppressed opengrep findings:")
    for r in findings:
        print(f"  {r['path']}:{r['start']['line']}  {r['check_id'].rsplit('.', 1)[-1]}")
    print(
        "\n  Fix the call, or suppress it with a reason comment above and\n"
        "  `# nosemgrep: <rule>` on the line DIRECTLY above the call.\n"
    )
    return len(findings)


def _report_stale(suppressed: set[tuple[str, int]]) -> int:
    stale = [
        marker
        for marker in _markers_in(_scanned_sources())
        # opengrep honours a marker on the finding's own line or the one above it.
        if (marker[0], marker[1]) not in suppressed and (marker[0], marker[1] + 1) not in suppressed
    ]
    if not stale:
        return 0
    print("Suppression markers that suppress nothing:")
    for path, line, text in stale:
        print(f"  {path}:{line}  {text[:90]}")
    print(
        "\n  Each either sits too far from its call (only the same line or the one\n"
        "  directly above counts) or is left over from a rewrite. Move it or delete\n"
        f"  it. Staleness is judged against {CONFIG} only.\n"
    )
    return len(stale)


def _resolve_opengrep() -> tuple[str | None, int]:
    """The opengrep binary, or None plus the exit code to return without it."""
    opengrep = shutil.which("opengrep")
    if opengrep is not None:
        return opengrep, 0
    # Under CI a skipped gate is indistinguishable from a passing one, which is
    # the failure this check exists to prevent — so it fails there, and only there.
    if os.environ.get("CI"):
        print(
            "ERROR  opengrep is not installed, and this gate cannot be skipped under CI.\n"
            "       Install it in the workflow before `make check`.",
            file=sys.stderr,
        )
        return None, 1
    print(
        "SKIP  opengrep not on PATH — skipping the scan.\n"
        "      Install it to run this gate locally; CI runs it either way.",
        file=sys.stderr,
    )
    return None, 0


def main(argv: list[str]) -> int:
    if any(a in ("-h", "--help") for a in argv):
        print(USAGE)
        return 0
    if argv:
        print(
            f"Error: unexpected argument: {argv[0]}. This tool takes no arguments.",
            file=sys.stderr,
        )
        return 2

    opengrep, code = _resolve_opengrep()
    if opengrep is None:
        return code

    try:
        active = _scan(opengrep, disable_nosem=False)
        revealed = _scan(opengrep, disable_nosem=True)

        if _report_errors([revealed, active]):
            return 1

        suppressed = _locations(revealed) - _locations(active)
        problems = _report_findings(active) + _report_stale(suppressed)
        if problems:
            print(f"{problems} problem(s).")
            return 1

        unjudged = len(_markers_in(_unscanned_sources()))
    except RuntimeError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 1

    tail = f" ({unjudged} marker(s) outside {'/'.join(SCAN_ROOTS)} not judged)" if unjudged else ""
    print(
        f"OK  opengrep clean over {'/'.join(SCAN_ROOTS)}; "
        f"{len(suppressed)} suppression(s) all still live{tail}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
