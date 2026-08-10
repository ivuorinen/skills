#!/usr/bin/env python3
"""One-shot patch: adjudicate Codacy's dangerous-subprocess-use-audit findings.

`scripts/hooks/` is under permissions.deny for the Edit/Write tools, so an agent
cannot apply this. Delete this file once applied.

    python3 docs/audit/apply-nosemgrep.py --check
    python3 docs/audit/apply-nosemgrep.py

Codacy reports "Detected subprocess function 'run' without a static string" on
`scripts/hooks/`. That is **not** bandit: `bandit -c pyproject.toml` reports zero
issues on those files, and bandit's own wording for the nearest checks (B603,
B607) differs. The rule is semgrep's
`python.lang.security.audit.dangerous-subprocess-use-audit`, which Codacy runs
through its own Semgrep tool, independently of the repo's bandit config.

So the `[tool.bandit]` skip list does not cover it, and the repo's own stated
convention applies instead — from that same block: "Everything else stays on,
including B105/B310, which are handled at the call site with a `# nosec` naming
the specific check and the reason." This does exactly that, for semgrep.

Six call sites, not the two Codacy currently reports: Codacy counts only issues
on changed lines, so the other four surface as soon as those lines move.
Suppressing all six now avoids re-litigating this per push.

Every argv here is built from a module constant or a literal list, with no
`shell=True` anywhere in the repo — the same reasoning `[tool.bandit]` records
for B603. The suppression is scoped to one line each; the rule stays live
everywhere else.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
H = REPO / "scripts" / "hooks"
TAG = "# nosemgrep: dangerous-subprocess-use-audit"

# {filename: [(description, anchor, replacement)]}
EDITS: dict[str, list[tuple[str, str, str]]] = {
    "post-bash-revalidate.py": [
        (
            "post-bash-revalidate: gate run",
            """            result = subprocess.run(
                cmd,""",
            f"""            # argv is a GATES entry: a module-constant literal list, never input.
            result = subprocess.run(  {TAG}
                cmd,""",
        ),
    ],
    "validate-rules-hook.py": [
        (
            "validate-rules-hook: validator run",
            """            result = subprocess.run(
                cmd,""",
            f"""            # argv is one of the two literal command lists in the loop above.
            result = subprocess.run(  {TAG}
                cmd,""",
        ),
    ],
    "stop-reminder.py": [
        (
            "stop-reminder: git read",
            """            result = subprocess.run(
                cmd,""",
            f"""            # argv is one of the three literal git read commands in the loop above.
            result = subprocess.run(  {TAG}
                cmd,""",
        ),
    ],
    "validate-audit-findings-hook.py": [
        (
            "validate-audit-findings-hook: per-file validate",
            """            result = subprocess.run(
                [*py, "validate", str(path)],""",
            f"""            # argv is `py` (interpreter + shipped tool path) plus literal words.
            result = subprocess.run(  {TAG}
                [*py, "validate", str(path)],""",
        ),
        (
            "validate-audit-findings-hook: store validate",
            """            result = subprocess.run(
                [*py, "validate"],""",
            f"""            # argv is `py` (interpreter + shipped tool path) plus a literal word.
            result = subprocess.run(  {TAG}
                [*py, "validate"],""",
        ),
        (
            "validate-audit-findings-hook: index regeneration",
            """        index = subprocess.run(
            [*py, "index"],""",
            f"""        # argv is `py` (interpreter + shipped tool path) plus a literal word.
        index = subprocess.run(  {TAG}
            [*py, "index"],""",
        ),
    ],
}


def apply_to(path: Path, edits: list[tuple[str, str, str]], write: bool) -> bool:
    """Apply `edits` to `path`. Returns True on success, False on drift."""
    rel = path.relative_to(REPO)
    if not path.exists():
        print(f"ERROR  {rel} not found", file=sys.stderr)
        return False
    text = original = path.read_text(encoding="utf-8")
    for desc, anchor, replacement in edits:
        if replacement in text:
            print(f"SKIP   {desc} (already applied)")
            continue
        found = text.count(anchor)
        if found != 1:
            print(
                f"ERROR  {desc}: anchor matched {found} times, want exactly 1.\n"
                f"       {rel} drifted — re-read it and update this script.",
                file=sys.stderr,
            )
            return False
        text = text.replace(anchor, replacement, 1)
        print(f"OK     {desc}")
    if write and text != original:
        path.write_text(text, encoding="utf-8")
        print(f"       -> wrote {rel}")
    return True


def main() -> int:
    """Verify every anchor across every file, then write."""
    ap = argparse.ArgumentParser(description="Suppress the semgrep audit rule at its call sites.")
    ap.add_argument("--check", action="store_true", help="verify anchors, write nothing")
    args = ap.parse_args()

    for name, edits in EDITS.items():
        if not apply_to(H / name, edits, write=False):
            return 1
    if args.check:
        print("\nAll anchors matched. Re-run without --check to apply.")
        return 0
    print()
    for name, edits in EDITS.items():
        if not apply_to(H / name, edits, write=True):
            return 1
    print("\nApplied. Next: run `make check`, then commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
