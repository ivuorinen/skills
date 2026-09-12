#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = "==3.11.*"
# ///
"""Reproduce Codacy's Agentlinter findings from a checkout, and gate on new ones.

Codacy runs three engines on this repository: opengrep, lizard and **Agentlinter**.
`make opengrep` closed the first gap — a rule that lived only in the Codacy UI and
was reproducible only by pushing. This target closes the third. On PR #131 the two
were compared directly: Codacy's `Agentlinter_clarity_*` ids map one-to-one onto
the local run's `clarity/*` rules and the reported word counts matched exactly, so
`npx agentlinter --local .` is the same engine Codacy reports from.

Three facts about the tool shape everything below.

**It always exits 0.** Findings, no findings, nothing to scan — all exit 0. So the
exit code carries no signal and this gate parses `--json` instead. A Makefile
recipe that simply ran the binary would pass unconditionally.

**`--local` is mandatory, not a preference.** `npx agentlinter [path]` is
documented as "Lint & share report (default)"; `--local` is the opt-out. The
report is not just scores — every diagnostic quotes the offending line back — so
the default uploads instruction-file contents to a third party. `--local` is
passed on every invocation here and must stay.

**Its high-severity rules are noisy on this repository.** At the time this gate
was written every `critical` and `error` diagnostic was a false positive:
`referenced-files-exist` missed `docs/audit/findings/INDEX.md` because it only
looks at the workspace root, `outdated-cross-references` reads a cited
`.claude/rules/*.md` path as a section heading, and `skill-safety/injection-vectors`
fired on `commands/prompt-safety.md` for containing the words it audits for. So
this gate does not fail on severity. It fails on a diagnostic that is **not in the
committed baseline** — the same shape as `/nitpicker baseline`: the accepted set
is recorded, and only what is new blocks.

A baseline entry that no longer fires is reported and does not fail. A fixed
finding breaking the build is the failure mode that teaches people to re-run a
gate until it passes; re-baseline at leisure with `--update`.

Diagnostics are keyed on (rule, file, message), deliberately without the line
number. Agentlinter's messages quote the offending text, so they distinguish
occurrences on their own, while line numbers drift on every edit above them —
keying on them would report the whole file as new after one inserted paragraph.

Usage:
    uv run --quiet scripts/check-agentlinter.py [<project_root>] [--update]

Exit codes:
    0  no new diagnostics (or baseline updated, or the run was skipped)
    1  new diagnostics, or the tool could not run under CI
    2  usage error
"""

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# The npm version npx fetches. Pinned because npx resolves `latest` at run time,
# and this package's npm releases are not verifiably built from its repository:
# the npm manifest declares no `repository`, is published by a different account
# than the source repo's, and its version lags the repo by a major. An unpinned
# fetch is an unreviewed third-party program executing inside the gate.
#
# That provenance is also why only THIS repo fetches it, and the shipped skill
# does not. `_conventions.md` forbids a command installing a tool onto a host it
# is auditing, and npx installs. Fetching it here is our own reviewed decision
# about our own tree; making that decision for someone else's is not ours.
PIN = "0.3.3"

# How to type this tool, for every message that advises running it.
# `.claude/rules/use-uv-runner.md`: internal tooling runs through uv, never a
# bare `python3` that can ignore the declared interpreter and script env. The
# path is spelled out too — `Path(__file__).name` alone does not resolve from
# the repo root, which is where anyone reading this advice is standing.
INVOKE = "uv run --quiet scripts/check-agentlinter.py"

BASELINE = ".agentlinter-baseline.json"
TIMEOUT = 300


def _key(d: dict) -> tuple[str, str, str]:
    return (str(d.get("rule", "")), str(d.get("file", "")), str(d.get("message", "")))


def _run(root: Path) -> dict | None:
    """Return the parsed report, or None when the tool could not produce one."""
    npx = shutil.which("npx")
    if npx is None:
        print("agentlinter: npx not found.", file=sys.stderr)
        return None
    try:
        # argv is a list and no shell is involved; every element but the scanned
        # root is a module constant, and the npx path is the one shutil.which
        # resolved. The marker must sit on the line directly above the call —
        # opengrep ignores it even one line further up, silently.
        # nosemgrep: dangerous-subprocess-use-audit
        proc = subprocess.run(
            [npx, "--yes", f"agentlinter@{PIN}", "--local", "--json", str(root)],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"agentlinter: invocation failed: {exc}", file=sys.stderr)
        return None
    if proc.stderr.strip():
        print(proc.stderr.rstrip(), file=sys.stderr)
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(f"agentlinter: output was not JSON: {exc}", file=sys.stderr)
        return None
    if not isinstance(report, dict) or not isinstance(report.get("diagnostics"), list):
        print("agentlinter: report has no `diagnostics` list.", file=sys.stderr)
        return None
    # Element types too, not just the container. `_key` calls `.get` on each one,
    # so a `null` or a scalar in the list raises AttributeError out of `main` —
    # a traceback instead of the clean skip-or-fail every other bad-report path
    # takes, and under CI a crash rather than a failed gate. The report comes
    # from a third-party binary whose provenance is the reason PIN exists.
    if any(not isinstance(d, dict) for d in report["diagnostics"]):
        print("agentlinter: `diagnostics` holds a non-object entry.", file=sys.stderr)
        return None
    return report


class _BaselineError(Exception):
    """The baseline exists but cannot be read."""


def _load_baseline(path: Path) -> tuple[Counter[tuple[str, str, str]], dict[str, str], str, bool]:
    """Raise `_BaselineError` rather than exiting: the callers disagree.

    Reading the baseline to judge a run is fatal when it fails. Reading it to
    preserve `reasons` while OVERWRITING it is not — and an earlier version
    exited from in here, which made `--update` die on precisely the corrupt file
    it is advertised to repair, printing its own advice back at the user.
    """
    if not path.is_file():
        return Counter(), {}, "", False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Shape first, because `_key` and `.get` below assume it. Valid JSON is
        # not a valid baseline: a top-level array, or `accepted: [null]`, would
        # otherwise raise AttributeError past this `except` and surface as a
        # traceback — and take `--update` down before it could rewrite the file,
        # which is the same dead end the exit-from-a-helper bug created.
        if not isinstance(data, dict):
            raise TypeError("baseline must be a JSON object")
        accepted = data["accepted"]
        if not isinstance(accepted, list) or any(not isinstance(d, dict) for d in accepted):
            raise TypeError("`accepted` must be a list of objects")
        reasons = data.get("reasons") or {}
        if not isinstance(reasons, dict):
            raise TypeError("`reasons` must be an object keyed by rule id")
        if any(not isinstance(why, str) for why in reasons.values()):
            raise TypeError("`reasons` values must be strings")
        # A blank reason is an absent one. Dropping it here routes it to the
        # unjustified report, which names the rule — where leaving it in would
        # satisfy a keys-only membership test and let `{"rule": ""}` stand in
        # for a justification, defeating the point of recording one.
        reasons = {rule: why for rule, why in reasons.items() if why.strip()}
        pin = str(data.get("pin", ""))
        return Counter(_key(d) for d in accepted), reasons, pin, True
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise _BaselineError(str(exc)) from exc


def _write_baseline(path: Path, report: dict) -> None:
    accepted = sorted(
        (
            {
                "rule": d.get("rule", ""),
                "file": d.get("file", ""),
                "severity": d.get("severity", ""),
                "message": d.get("message", ""),
            }
            for d in report["diagnostics"]
        ),
        key=lambda d: (d["rule"], d["file"], d["message"]),
    )
    # Reasons are hand-written and survive a re-record. Regenerating them away
    # would mean every `--update` silently discarded the justifications, which
    # is the state this field exists to prevent.
    #
    # Best-effort, because this is the repair path: an unreadable baseline must
    # not block the command that rewrites it. The reasons in an unparseable file
    # are unrecoverable anyway, and dropping them is self-correcting — the next
    # gate run fails every rule as unjustified, which is the right outcome after
    # a baseline was corrupted.
    try:
        _, reasons, _, _ = _load_baseline(path)
    except _BaselineError as exc:
        reasons = {}
        print(
            f"warning: {BASELINE} was unreadable ({exc}); reasons not preserved.", file=sys.stderr
        )
        print("Re-justify each rule — the next gate run will list them.", file=sys.stderr)
    path.write_text(
        json.dumps(
            {"pin": PIN, "reasons": reasons, "accepted": accepted}, indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"OK  {BASELINE} updated: {len(accepted)} accepted diagnostic(s).")


def _parse(argv: list[str]) -> tuple[Path, bool]:
    """Return (root, update), or exit 2 on a usage error."""
    positional = [a for a in argv if not a.startswith("-")]
    unknown = [a for a in argv if a.startswith("-") and a != "--update"]
    if unknown or len(positional) > 1:
        bad = unknown or positional[1:]
        print(f"Error: unexpected argument(s): {bad}", file=sys.stderr)
        print(f"Usage: {INVOKE} [<project_root>] [--update]", file=sys.stderr)
        sys.exit(2)
    root = Path(positional[0]).resolve() if positional else REPO_ROOT
    if not root.is_dir():
        print(f"Error: not a directory: {root}", file=sys.stderr)
        sys.exit(2)
    return root, "--update" in argv


def _skip_or_fail(update: bool) -> int:
    """The tool could not produce a report.

    Locally this degrades to a skip so an offline clone can still run `make
    check`; under CI it fails, because a gate that skips silently is not a gate.
    Same split `make opengrep` makes, for the same reason.

    `--update` never skips. Re-recording needs a report by definition, so a skip
    there would exit 0 having written nothing — leaving the contributor believing
    a diagnostic was accepted while CI keeps failing on the unchanged baseline.
    """
    if update:
        print("agentlinter: no report, so there is nothing to re-record.", file=sys.stderr)
        return 1
    if os.environ.get("CI"):
        print("agentlinter: required under CI — failing.", file=sys.stderr)
        return 1
    print("agentlinter: skipped (see above). Not a clean result.")
    return 0


def _report_unjustified(rules: list[str]) -> int:
    """A baselined rule with no recorded reason.

    The whole risk of a baseline is that it stops being a record of judgements
    and becomes a place to put things that were never looked at — and from the
    file alone the two are indistinguishable. Requiring a reason per rule makes
    silencing a NEW rule class cost a sentence explaining why it is noise. It is
    the same job `check-opengrep.py` does when it fails a `# nosemgrep` that
    suppresses nothing: a suppression has to keep earning its place.

    Keyed by rule, not by entry: why a rule's hits are noise is a property of
    the rule. A new hit of an already-justified rule is not silently absorbed —
    it is not in `accepted`, so it fails as a new diagnostic first.
    """
    print(f"\n{len(rules)} baselined rule(s) with no recorded reason:", file=sys.stderr)
    for rule in rules:
        print(f"  {rule}", file=sys.stderr)
    print(
        f"\nAdd an entry per rule under `reasons` in {BASELINE}, saying why its hits\n"
        "are noise here. A rule nobody can justify is a rule to fix, not to baseline.",
        file=sys.stderr,
    )
    return 1


def _baseline_for_reading(
    path: Path,
) -> tuple[Counter[tuple[str, str, str]], dict[str, str]] | None:
    """The baseline as a gate run needs it, or None having said why not.

    Both failures are fatal to a gate run and neither is to `--update`, which is
    why this lives here and not in `_load_baseline`.
    """
    try:
        accepted, reasons, pin, existed = _load_baseline(path)
    except _BaselineError as exc:
        print(f"{BASELINE} is unreadable: {exc}", file=sys.stderr)
        print(f"Regenerate it with: {INVOKE} --update", file=sys.stderr)
        return None
    if not existed:
        print(f"Error: {BASELINE} not found under {path.parent}.", file=sys.stderr)
        print(f"Create it with: {INVOKE} --update", file=sys.stderr)
        return None
    # A baseline recorded under another agentlinter carries another rule set, so
    # its accepted entries are judgements about a different tool. Rejected here
    # rather than in `_load_baseline`, because `--update` rewrites the pin and
    # must not be blocked by the mismatch it repairs.
    if pin != PIN:
        print(
            f"{BASELINE} was recorded by agentlinter@{pin or '?'}, PIN is {PIN}.", file=sys.stderr
        )
        print(f"Re-record it against the pinned version: {INVOKE} --update", file=sys.stderr)
        return None
    return accepted, reasons


def _diff(
    report: dict, accepted: Counter[tuple[str, str, str]]
) -> tuple[list[dict], list[tuple[str, str, str]], int]:
    """New diagnostics, no-longer-firing baseline entries, and the total.

    Counted rather than set-differenced. The key drops the line number on
    purpose, so two identical offending lines in one file share a key — and a
    plain set difference reports nothing new once the first is baselined, which
    lets a second copy of an accepted defect through. Counting keeps
    multiplicity while staying immune to the line drift that keying on `line`
    would import.
    """
    current = Counter(_key(d) for d in report["diagnostics"])
    example: dict[tuple[str, str, str], dict] = {}
    for d in report["diagnostics"]:
        example.setdefault(_key(d), d)
    new = [example[k] for k in sorted(current) for _ in range(current[k] - accepted[k])]
    stale = sorted(k for k in accepted if accepted[k] > current[k])
    return new, stale, sum(current.values())


def _report_new(new: list[dict]) -> None:
    print(f"\n{len(new)} NEW diagnostic(s):", file=sys.stderr)
    for d in new:
        where = f"{d.get('file', '?')}:{d.get('line')}" if d.get("line") else d.get("file", "?")
        print(f"  [{d.get('severity', '?')}] {d.get('rule', '?')}  {where}", file=sys.stderr)
        print(f"      {d.get('message', '')}", file=sys.stderr)
        if d.get("fix"):
            print(f"      fix: {d['fix']}", file=sys.stderr)
    print(
        f"\nFix them, or accept them with: {INVOKE} --update",
        file=sys.stderr,
    )


def main(argv: list[str]) -> int:
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    root, update = _parse(argv)

    report = _run(root)
    if report is None:
        return _skip_or_fail(update)

    baseline_path = root / BASELINE
    if update:
        _write_baseline(baseline_path, report)
        return 0

    loaded = _baseline_for_reading(baseline_path)
    if loaded is None:
        return 1
    accepted, reasons = loaded

    new, stale, total = _diff(report, accepted)

    score = report.get("score", "?")
    print(f"agentlinter@{PIN}: score {score}/100, {total} diagnostic(s).")

    if stale:
        print(f"\n{len(stale)} baseline entry(ies) no longer fire — re-baseline when convenient:")
        for rule, file, message in stale:
            print(f"  {rule}  {file}  {message[:90]}")

    orphaned = sorted(r for r in reasons if not any(k[0] == r for k in accepted))
    if orphaned:
        print(f"\n{len(orphaned)} reason(s) for rules no longer baselined: {', '.join(orphaned)}")

    if new:
        _report_new(new)
        return 1

    if unjustified := sorted({k[0] for k in accepted} - reasons.keys()):
        return _report_unjustified(unjustified)

    print("OK  no new agentlinter diagnostics.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
