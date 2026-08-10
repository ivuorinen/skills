#!/usr/bin/env python3
"""One-shot patch: docstring every function in scripts/hooks/.

`scripts/hooks/` is under permissions.deny for the Edit/Write tools, so an agent
cannot apply this. Anchored string replacements, not a diff, so it fails loudly
on drift. Delete this file once applied — the change lives in git from then on.

    python3 docs/audit/apply-hook-docstrings.py --check
    python3 docs/audit/apply-hook-docstrings.py

Thirteen functions carried no docstring, every `main()` among them. Each new
docstring states why rather than what, per the Documentation section of
skills/nitpicker/commands/_conventions.md: the failure the function prevents,
the invariant it holds, or the reason a surprising line reads as it does.
Docstrings add no branches, so coverage is unaffected.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
H = REPO / "scripts" / "hooks"


def _doc(anchor: str, body: str, indent: str = "    ") -> tuple[str, str]:
    """Build an (anchor, replacement) pair that inserts `body` under `anchor`."""
    lines = body.strip("\n").split("\n")
    doc = f'{indent}"""' + lines[0]
    if len(lines) > 1:
        doc += "\n" + "\n".join(f"{indent}{ln}".rstrip() for ln in lines[1:])
        doc += f'\n{indent}"""'
    else:
        doc += '"""'
    return anchor, f"{anchor}\n{doc}"


EDITS: dict[str, list[tuple[str, str, str]]] = {
    "_hooklib.py": [
        (
            "_hooklib: take",
            *_doc(
                "    def take(match: re.Match[str]) -> str:",
                """
Record one quoted span and return its opaque placeholder.

The placeholder carries the span's index in `spans`, so `_unmask`
restores the exact original text rather than a re-quoted approximation.
The NUL delimiters keep it from colliding with anything a real shell
command can contain.
""",
                indent="        ",
            ),
        ),
    ],
    "check-version-sync-hook.py": [
        (
            "check-version-sync-hook: main",
            *_doc(
                "def main() -> None:",
                """
Re-run the version-sync checker after an edit to a version manifest.

The five manifests drift silently — nothing else reads them together, so
a hand-edit to one ships a release whose plugin and package versions
disagree. Exits 2 with the mismatching lines, the only channel a
PostToolUse hook has back to the agent.
""",
            ),
        ),
    ],
    "deny-agents-path-hook.py": [
        (
            "deny-agents-path-hook: _canonicalize",
            *_doc(
                "def _canonicalize(command: str) -> str:",
                """
Fold the spellings a shell resolves identically into one comparable form.

Escaped separators, quotes, backslashes, repeated slashes and `.`
segments all reach the same path, so without this the textual pass misses
every obfuscated spelling of the same target.

Glob metacharacters are deliberately left intact: stripping the `?` in
`.?laude` collapses it to `.laude` and hides a match the glob-expansion
pass would otherwise catch.
""",
            ),
        ),
        (
            "deny-agents-path-hook: main",
            *_doc(
                "def main() -> None:",
                """
Block a Bash command that reaches one of the protected trees.

Two denials rather than one, because permissions.deny protects the two
surfaces differently: any reference to `.claude/agents/`, but only a
write to `scripts/hooks/` or `.claude/settings.json`, where Read stays
allowed. Exit 2 is a PreToolUse deny and surfaces stderr to the agent.
""",
            ),
        ),
    ],
    "deny-unsafe-git-hook.py": [
        (
            "deny-unsafe-git-hook: main",
            *_doc(
                "def main() -> None:",
                """
Block the git writes the rules declare unenforced.

Every git invocation in the command is judged, not just the first:
`echo hi && git push origin main` reaches a protected branch through its
second stage, and a guard reading only stage one would pass it. Exit 2 is
a PreToolUse deny.
""",
            ),
        ),
    ],
    "post-bash-revalidate.py": [
        (
            "post-bash-revalidate: main",
            *_doc(
                "def main() -> None:",
                """
Re-run the whole-tree gates when a Bash call dirtied a governed path.

A Bash event carries no `file_path`, so this asks git what is dirty
instead of reading the event — that is the whole reason the hook exists,
since the Write/Edit validators never see a `sed -i` or a redirection.
Returns silently on a clean tree; exits 2 with the failing gate's output.
""",
            ),
        ),
    ],
    "ruff-hook.py": [
        (
            "ruff-hook: main",
            *_doc(
                "def main() -> None:",
                """
Auto-fix and format an edited Python file, then report what remains.

Fix and format are captured and reported alongside the final check: a
fix or format pass that itself fails (bad config, a syntax error) would
otherwise leave the check reporting a lint failure whose real cause
appears nowhere in the output.
""",
            ),
        ),
    ],
    "stop-reminder.py": [
        (
            "stop-reminder: main",
            *_doc(
                "def main() -> None:",
                """
Remind about uncommitted skill files before Claude hands back control.

Reads the index, the working tree and the untracked set: a brand-new
SKILL.md or command file appears in neither diff form, yet is the most
common pending change. Exit 2 blocks the stop, which is why the
`stop_hook_active` guard is needed to keep the reminder from firing again
on its own forced continuation.
""",
            ),
        ),
    ],
    "validate-audit-findings-hook.py": [
        (
            "validate-audit-findings-hook: store_root",
            *_doc(
                "def store_root(repo_root: Path) -> Path:",
                """
The findings store directory for a repo root.

One definition, so this hook and findings.py cannot disagree about where
the store lives.
""",
            ),
        ),
        (
            "validate-audit-findings-hook: should_check",
            *_doc(
                "def should_check(path: Path, repo_root: Path) -> bool:",
                """
True if `path` is an open finding file this hook must validate.

INDEX.md and the resolved ledger are generated rather than hand-authored,
so they are excluded here and handled by their own branches in `main`.
""",
            ),
        ),
        (
            "validate-audit-findings-hook: main",
            *_doc(
                "def main() -> None:",
                """
Validate an edited findings file and regenerate INDEX.md.

The index is regenerated on every store edit, not only on a finding edit,
so it cannot drift from the files it summarises. `make check` fails on a
stale INDEX.md, so drift found here is drift not found in CI.
""",
            ),
        ),
    ],
    "validate-rules-hook.py": [
        (
            "validate-rules-hook: main",
            *_doc(
                "def main() -> None:",
                """
Validate an edited rule file, and the anatomy of the whole rules tree.

Two checks rather than one: validate-rules.py judges the edited file,
while check-rules-anatomy.py judges the tree — catching a rule that is
well-formed on its own but stale against the paths it names.
""",
            ),
        ),
    ],
    "ask-destructive-restore-hook.py": [
        (
            "ask-destructive-restore-hook: _decide",
            *_doc(
                "def _decide(decision: str, reason: str) -> None:",
                """
Emit a PreToolUse permission decision on stdout and exit.

This hook asks rather than denies, so it speaks the structured
`hookSpecificOutput` protocol instead of the exit-2 channel its sibling
guards use. Exits 0: a non-zero exit here would be read as a hook failure
rather than as the decision it carries.
""",
            ),
        ),
        (
            "ask-destructive-restore-hook: main",
            *_doc(
                "def main() -> None:",
                """
Ask before a git restore discards uncommitted work.

Stays silent when the target is clean, so ordinary reverts are not
interrupted — the prompt is reserved for the case where the discarded
content exists nowhere else: `git checkout --` overwrites the working
tree from the index, leaving no reflog entry and no stash to recover
from. The listed paths are truncated because the prompt has to stay
readable to be read at all.
""",
            ),
        ),
    ],
    "guard-ctx-ok-hook.py": [
        (
            "guard-ctx-ok-hook: _deny",
            *_doc(
                "def _deny(reason: str) -> None:",
                """
Block the call and name both the reason and the way out.

The message states the alternative rather than only the refusal: a denial
that does not say what to run instead invites the same command back with
a different spelling.
""",
            ),
        ),
        (
            "guard-ctx-ok-hook: main",
            *_doc(
                "def main() -> None:",
                """
Validate a claimed `# ctx-ok` escape hatch.

Only commands that claim the hatch are judged — an unmarked command is
the routing guard's business, not this one's. Every verb in the command
is checked, not just the first, so appending a mutation to a read does
not launder the read past the hatch.
""",
            ),
        ),
    ],
    "validate-json-hook.py": [
        (
            "validate-json-hook: main",
            *_doc(
                "def main() -> None:",
                """
Reject malformed JSON the moment it is written.

A broken manifest or settings file otherwise surfaces far from the edit
that caused it — as a plugin that fails to load, or a hook that silently
stops running. An unreadable file is not this hook's failure to report,
so `OSError` passes rather than blocking the edit.
""",
            ),
        ),
    ],
    "validate-skill-hook.py": [
        (
            "validate-skill-hook: main",
            *_doc(
                "def main() -> None:",
                """
Validate a skill or command file after Write or Edit.

A command-file edit is validated through its parent SKILL.md: the checks
that matter most — table/file sync and dispatch format — are properties
of the pair, and are invisible when a command file is judged alone.
""",
            ),
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
    ap = argparse.ArgumentParser(description="Docstring the scripts/hooks/ functions.")
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
