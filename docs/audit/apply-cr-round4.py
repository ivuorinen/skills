#!/usr/bin/env python3
"""One-shot patch: report a failed ruff fix/format even when the check passes.

`scripts/hooks/` is under permissions.deny for the Edit/Write tools. Delete this
file once applied.

    python3 docs/audit/apply-cr-round4.py --check
    python3 docs/audit/apply-cr-round4.py

The previous round stopped a later tool *error* from discarding a completed
validator failure. It fixed only the exception arm. The success path had the
same hole: `if result.returncode != 0` means a non-zero `fix` or `fmt` with a
clean final check returns silently, and the fix/format output is the only place
that cause appears — which is the exact reason those two results are captured,
as the comment above them says.

The condition now covers all three completed calls. Ordering is preserved
(fix, fmt, result), so a report that previously read prefix-then-result still
reads the same way.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

HOOK_EDITS: list[tuple[str, str, str]] = [
    (
        "ruff-hook: report any completed failure, not only the final check",
        """    if result.returncode != 0:
        prefix = "".join(r.stdout + r.stderr for r in (fix, fmt) if r.returncode != 0)
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        print((prefix + result.stdout + result.stderr).rstrip(), file=sys.stderr, flush=True)
        sys.exit(2)""",
        """    # Every completed call counts, not just the last. A fix or format pass that
    # failed on its own (bad config, a syntax error) is reported even when the
    # final check comes back clean: its output is the only place that cause
    # appears, which is why both results are captured at all. Ordering is
    # fix, fmt, result, so the report reads as it always did.
    failed = [r for r in (fix, fmt, result) if r.returncode != 0]
    if failed:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        report = "".join(r.stdout + r.stderr for r in failed)
        print(report.rstrip(), file=sys.stderr, flush=True)
        sys.exit(2)""",
    ),
]

TEST_EDITS: list[tuple[str, str, str]] = [
    (
        "tests: a failed fix surfaces even when the check passes",
        """    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_validate_rules_hook_keeps_a_completed_failure(monkeypatch, tmp_path, capsys):""",
        '''    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_ruff_hook_reports_a_failed_fix_when_the_check_passes(monkeypatch, tmp_path, capsys):
    """`ruff check --fix` failing on its own — bad config, a syntax error — while
    the final check comes back clean. The fix pass's output is the only place
    that cause appears, so returning silently loses it entirely."""
    mod = _load("ruff-hook")
    target = tmp_path / "x.py"
    target.write_text("x = 1\\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/ruff")
    calls = []

    def _run_ruff(cmd, *a, **k):
        """Fail the --fix pass; pass the format and the final check."""
        calls.append(cmd)
        if len(calls) == 1:
            return _Result(returncode=2, stderr="ruff: bad configuration\\n")
        return _Result()

    monkeypatch.setattr(mod.subprocess, "run", _run_ruff)
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    assert exc.value.code == 2
    assert "bad configuration" in capsys.readouterr().err


def test_validate_rules_hook_keeps_a_completed_failure(monkeypatch, tmp_path, capsys):''',
    ),
]

TARGETS: list[tuple[Path, list[tuple[str, str, str]]]] = [
    (REPO / "scripts" / "hooks" / "ruff-hook.py", HOOK_EDITS),
    (REPO / "tests" / "test_hooks.py", TEST_EDITS),
]


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
    """Verify every anchor across both files, then write."""
    ap = argparse.ArgumentParser(description="Report completed ruff failures.")
    ap.add_argument("--check", action="store_true", help="verify anchors, write nothing")
    args = ap.parse_args()

    for path, edits in TARGETS:
        if not apply_to(path, edits, write=False):
            return 1
    if args.check:
        print("\nAll anchors matched. Re-run without --check to apply.")
        return 0
    print()
    for path, edits in TARGETS:
        if not apply_to(path, edits, write=True):
            return 1
    print("\nApplied. Next: run `make check`, then commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
