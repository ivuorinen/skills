#!/usr/bin/env python3
"""One-shot patch: docstring every function in the two hook test modules.

Ninety-eight functions carried no docstring — test bodies, module-level helpers,
and the nested fakes that stand in for `subprocess.run`. Each new docstring
states what the function pins or simulates, per the Documentation section of
`skills/nitpicker/commands/_conventions.md`.

Insertion points come from the AST, not from the recorded line number, so a
multi-line `def` signature gets its docstring after the closing paren rather
than in the middle of the parameter list. Each entry is keyed by the `def`
line it was authored against and is verified against the parsed name before
anything is written, so a drifted file aborts the run instead of inserting
prose into the wrong function.

    python3 docs/audit/apply-test-docstrings.py --check
    python3 docs/audit/apply-test-docstrings.py

Delete this file once applied — the change lives in git from then on.
"""

import argparse
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# {relative path: {def line: (expected name, docstring)}}
INSERTS: dict[str, dict[int, tuple[str, str]]] = {
    "tests/test_hooks.py": {
        32: ("_load", "Import a hook module by its hyphenated filename."),
        39: ("_run", "Drive a hook's main() with `stdin_text` as its event payload."),
        56: (
            "test_empty_stdin_is_silent_noop",
            "No event means nothing to judge: the hook returns without output.",
        ),
        63: (
            "test_non_dict_payload_is_silent_noop",
            "A JSON `null` or list payload must not crash on data.get(...).",
        ),
        72: (
            "test_irrelevant_path_is_silent_noop",
            "A hook that fires on every edit must stay quiet for files it does not own.",
        ),
        86: ("test_validate_json_valid_file_passes", "Well-formed JSON produces no output."),
        96: (
            "test_validate_json_invalid_file_exits_2_with_stderr",
            "Exit 2 plus stderr is the only channel a PostToolUse hook has back to the agent.",
        ),
        108: (
            "test_validate_json_unreadable_path_fails_open",
            "An unreadable path is not this hook's defect, so it must not block the edit.",
        ),
        125: (
            "test_validate_skill_bad_structure_exits_2",
            "A malformed SKILL.md must be reported at the edit, not left for CI.",
        ),
        151: (
            "test_version_sync_mismatch_exits_2",
            "The five manifests drift silently; only this hook reads them together at edit time.",
        ),
        181: (
            "test_ruff_hook_lint_error_exits_2",
            "A lint error --fix cannot remove has to surface rather than pass quietly.",
        ),
        202: ("_boom", "Fail the test if ruff is invoked when the binary is absent."),
        218: ("_hooklib", "Load _hooklib fresh, so env changes are read at import time."),
        229: (
            "test_repo_root_empty_claude_project_dir_falls_through",
            "An empty env value counts as absent: Path('') is Path('.'), which would silently "
            "move every hook's containment boundary to the working directory.",
        ),
        246: (
            "test_repo_root_both_empty_falls_back_to_parents",
            "With neither variable usable, the computed parent of scripts/hooks/ is the root.",
        ),
        258: ("_run", "Return staged or worktree paths depending on the git argv."),
        261: ("_Result", "Stand-in for CompletedProcess with NUL-separated stdout."),
        270: (
            "test_stop_reminder_flags_staged_skill",
            "A staged SKILL.md is the case the reminder exists for.",
        ),
        305: (
            "test_stop_reminder_flags_staged_command_file",
            "Command files count as skill changes too, not just SKILL.md itself.",
        ),
        315: (
            "test_stop_reminder_silent_when_no_staged_skill",
            "Dirty non-skill paths must stay quiet in either scope.",
        ),
        324: (
            "test_stop_reminder_silent_when_nothing_staged",
            "A clean tree produces no reminder.",
        ),
        336: ("_boom", "Fail the test if git runs once stop_hook_active is set."),
        348: (
            "test_deny_agents_blocks_cd_bypass",
            "`cd` into the protected tree shifts the glob base; the guard resolves it anyway.",
        ),
        356: (
            "test_deny_agents_blocks_double_slash",
            "A repeated separator reaches the same path, so canonicalisation must fold it.",
        ),
        364: (
            "test_deny_agents_allows_unrelated_command",
            "A sibling .claude/ path is not the agents tree and must not be blocked.",
        ),
        373: (
            "test_deny_agents_blocks_dot_segment",
            "A `.` segment reaches the same path and must not hide the match.",
        ),
        381: (
            "test_deny_agents_blocks_escaped_slash",
            "An escaped separator is still a separator to the shell.",
        ),
        419: (
            "test_deny_agents_allows_agents_word_without_path",
            "Both tokens present but not as a path into the tree — grepping rules for the "
            "word must not false-positive.",
        ),
        436: (
            "test_deny_agents_absolute_glob_does_not_crash",
            "Path.glob raises on some absolute patterns; the guard swallows that rather "
            "than crashing open.",
        ),
        455: (
            "test_deny_agents_blocks_content_addressed_reach",
            "A command naming the file rather than the directory carries no path token, "
            "so the bare filename is matched instead.",
        ),
        496: (
            "test_deny_agents_filename_match_is_token_bounded",
            "Substring matching would also block a different file whose name merely "
            "starts with a protected one.",
        ),
        964: ("_failing_run", "Simulate a validator that exits non-zero with a violation."),
        965: ("_R", "Stand-in for a failed CompletedProcess."),
        985: ("_run_git", "Return an untracked-only path set, mimicking ls-files --others."),
        989: ("_R", "Stand-in for CompletedProcess with NUL-separated stdout."),
        1084: (
            "test_deny_agents_hook_runs_as_a_script",
            "The __main__ path must behave like the imported one — it is how the hook "
            "actually runs.",
        ),
        1096: (
            "test_stop_reminder_runs_as_a_script",
            "The __main__ path must behave like the imported one.",
        ),
        1099: ("_fake_git", "Report a staged command file, and nothing in the worktree."),
        1147: (
            "test_validate_json_non_existent_path_is_a_silent_noop",
            "A deleted or renamed file is not a JSON defect.",
        ),
        1167: ("_R", "Stand-in for a checker that failed with output on stdout."),
        1185: ("_R", "Stand-in for git reporting 'not a repository'."),
        1252: (
            "test_deny_agents_allows_non_path_tokens_that_break_glob",
            "Ordinary tokens carrying glob metacharacters must not deny the call.",
        ),
        1270: ("_pre_313", "Reproduce CPython <3.13 raising on an adjacent '**' pattern."),
        1292: ("_raises", "Simulate glob refusing a pattern with OSError."),
        1303: (
            "_findings_repo",
            "Build a tmp repo carrying a real copy of the shipped findings.py.",
        ),
        1313: (
            "test_audit_findings_ignores_a_path_outside_the_store",
            "An edit outside docs/audit/findings/ must not invoke findings.py at all.",
        ),
        1324: ("_never_run", "Build a fake that fails the test if it is ever called."),
        1325: ("_boom", "Fail the test with the caller's message."),
        1358: ("_R", "Stand-in for an index regeneration that failed."),
        1379: (
            "test_ruff_hook_silent_when_ruff_is_clean",
            "A clean file produces no output and no exit.",
        ),
        1391: (
            "test_version_sync_hook_silent_when_versions_agree",
            "Matching manifests produce no output.",
        ),
        1403: (
            "test_validate_skill_hook_silent_when_the_skill_is_valid",
            "A valid skill produces no output.",
        ),
        1433: ("_ok", "Record the argv and report success."),
        1457: ("_Result", "Stand-in for CompletedProcess in the revalidate tests."),
        1458: ("__init__", "Store the three fields the hook reads."),
        1485: (
            "_fake_run",
            "Dispatch on argv: git status returns `status`, everything else is a gate. "
            "An exception instance is raised rather than returned, which is how the "
            "timeout and OSError arms are driven.",
        ),
        1503: ("_gate_calls", "The recorded argv list with the git status call removed."),
        1610: ("_boom", "Simulate uv absent from PATH."),
        1628: ("_hang", "Simulate ruff exceeding its timeout."),
        1642: ("_boom", "Simulate git absent from PATH."),
        1714: (
            "test_guard_allows_reads_and_unrelated_writes",
            "Read is not denied on these paths, so blocking a read would contradict the "
            "permission model and break ordinary work.",
        ),
        1724: (
            "test_guard_denial_message_names_the_surface",
            "A denial that does not say what is protected, or that reading is still "
            "allowed, invites the same command back in a different spelling.",
        ),
        1745: (
            "test_revalidate_ignores_a_dirty_path_outside_the_governed_set",
            "An ungoverned dirty path must not trigger the whole-tree gates.",
        ),
        1803: (
            "test_revalidate_exits_2_with_the_failing_gate_output",
            "The agent sees only stderr, so the failing gate's own output has to reach it.",
        ),
        1804: ("_gate", "Fail the skill validator, pass everything else."),
        1822: ("_gate", "Fail the version-sync gate with blank output."),
        1856: ("_fake_run", "Report a governed dirty path, then fail every gate."),
        1883: ("read", "Raise while reading stdin, to drive the fail-closed arm."),
        1887: ("_bash", "Wrap a shell command in a PreToolUse Bash event payload."),
        2042: (
            "test_git_guard_allows_ordinary_commands",
            "The guard must not obstruct routine git use.",
        ),
        2050: (
            "test_git_guard_denies_push_to_protected_refspec",
            "An explicit refspec reaches main regardless of what HEAD is.",
        ),
        2058: (
            "test_git_guard_allows_push_to_a_feature_refspec",
            "Pushing a feature branch is the intended path and stays allowed.",
        ),
        2178: (
            "test_git_guard_current_branch_reads_git",
            "HEAD decides when no refspec does, so the branch is read from git itself.",
        ),
        2225: (
            "test_ctx_ok_guard_denies_the_hatch_on_read_commands",
            "The hatch is for a state mutation; claiming it on a read is what it exists to catch.",
        ),
        2245: (
            "test_ctx_ok_guard_allows_must_run_direct_and_unclaimed",
            "An unmarked command belongs to the routing guard, not this one.",
        ),
        2368: ("test_ctx_ok_guard_ignores_an_empty_command", "An empty command claims nothing."),
        2374: (
            "test_ctx_ok_guard_runs_as_a_script_and_fails_closed",
            "The __main__ path must deny too — a guard that exits 0 on error enforces nothing.",
        ),
        2391: ("_restore_mod", "Load the restore guard with git status faked to `dirty`."),
        2400: ("_ask_payload", "The structured permission decision the hook wrote to stdout."),
        2408: (
            "test_restore_guard_asks_when_the_target_is_dirty",
            "Uncommitted content at the target exists nowhere else — no reflog, no stash.",
        ),
        2430: (
            "test_restore_guard_ignores_non_restore_commands",
            "Only the discarding forms are the guard's business.",
        ),
        2437: (
            "test_restore_guard_silent_when_the_target_is_clean",
            "A clean target means an ordinary revert; interrupting it would train the "
            "prompt to be ignored.",
        ),
        2452: (
            "test_restore_guard_truncates_a_long_dirty_list",
            "A prompt has to stay readable to be read at all.",
        ),
        2474: (
            "test_restore_guard_drops_flags_from_the_target_list",
            "Flags are not paths; treating them as targets would report nonsense.",
        ),
        2520: (
            "test_restore_guard_matches_files_under_a_directory_target",
            "A directory target discards every dirty file beneath it, not just an exact match.",
        ),
        2578: (
            "test_restore_guard_runs_as_a_script_and_fails_closed",
            "The __main__ path must ask rather than allow when it cannot judge.",
        ),
    },
    "tests/test_validate_audit_findings_hook.py": {
        19: ("_store_file", "Create a file under a tmp repo, making parents as needed."),
        26: (
            "test_should_check_accepts_finding_file",
            "An open finding file is the case the hook validates.",
        ),
        31: (
            "test_should_check_rejects_index_and_outsiders",
            "INDEX.md is generated, and neither an outsider nor a non-markdown file is a finding.",
        ),
        40: (
            "test_should_check_rejects_missing_file",
            "A deleted finding has nothing to validate.",
        ),
        45: (
            "test_should_check_matches_under_symlinked_repo_root",
            "The caller resolves the edited path, so the root must resolve too — otherwise "
            "a symlinked checkout silently disables the hook.",
        ),
        56: ("test_main_ignores_invalid_json", "An unparseable event is not the hook's to report."),
        78: ("_boom", "Simulate python3 or findings.py absent from PATH."),
        104: (
            "test_main_accepts_legacy_toplevel_payload",
            "Older events carry file_path at the top level rather than under tool_input.",
        ),
        118: ("test_main_noop_without_path", "No path in the event means nothing to validate."),
        124: (
            "test_main_regenerates_index_for_valid_finding",
            "The index is regenerated on every store edit so it cannot drift from the "
            "files it summarises.",
        ),
        148: (
            "test_main_regenerated_index_uses_relative_paths",
            "Absolute paths leak the checkout directory and fail make check's index-check.",
        ),
        177: (
            "test_main_handles_resolved_ledger_edit",
            "The ledger has no per-line file, so it is store-validated rather than "
            "per-file validated.",
        ),
    },
}


def _render(doc: str, indent: str) -> list[str]:
    """Format `doc` as a docstring block at `indent`, wrapping past one line."""
    if len(indent) + len(doc) + 6 <= 100 and "\n" not in doc:
        return [f'{indent}"""{doc}"""']
    words, lines, cur = doc.split(), [], ""
    for w in words:
        if cur and len(indent) + len(cur) + 1 + len(w) > 96:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    return [f'{indent}"""{lines[0]}'] + [f"{indent}{ln}" for ln in lines[1:]] + [f'{indent}"""']


def apply_to(rel: str, spec: dict[int, tuple[str, str]], write: bool) -> bool:
    """Insert every docstring in `spec` into `rel`. False on drift."""
    path = REPO / rel
    if not path.exists():
        print(f"ERROR  {rel} not found", file=sys.stderr)
        return False
    src = path.read_text(encoding="utf-8").splitlines()
    tree = ast.parse("\n".join(src))

    by_line = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            by_line[node.lineno] = node

    # Already applied: every recorded line has shifted, so the name check below
    # would report drift on a file that is in fact complete. Detect the finished
    # state first, which is what makes a re-run a no-op rather than an error.
    if not any(
        isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and not ast.get_docstring(n)
        for n in ast.walk(tree)
    ):
        print(f"SKIP   {rel} (already applied)")
        return True

    done = skipped = 0
    edits = []
    for lineno, (name, doc) in sorted(spec.items(), reverse=True):
        node = by_line.get(lineno)
        if node is None or node.name != name:
            found = node.name if node else "nothing"
            print(
                f"ERROR  {rel}:{lineno} expected `{name}`, found {found}.\n"
                f"       The file drifted — re-read it and update this script.",
                file=sys.stderr,
            )
            return False
        if ast.get_docstring(node):
            skipped += 1
            continue
        first = node.body[0]
        indent = " " * (first.col_offset)
        block = _render(doc, indent)
        # ruff format wants a blank line between a docstring and a following
        # class or def; without it `make format-check` fails on the result.
        if isinstance(node, ast.ClassDef) or isinstance(
            first, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            block.append("")
        edits.append((first.lineno - 1, block))
        done += 1

    for at, block in edits:  # already sorted descending, so indices stay valid
        src[at:at] = block

    print(f"OK     {rel}: {done} inserted, {skipped} already present")
    if write and edits:
        path.write_text("\n".join(src) + "\n", encoding="utf-8")
        print(f"       -> wrote {rel}")
    return True


def main() -> int:
    """Verify every anchor across both files, then write."""
    ap = argparse.ArgumentParser(description="Docstring the hook test modules.")
    ap.add_argument("--check", action="store_true", help="verify anchors, write nothing")
    args = ap.parse_args()

    for rel, spec in INSERTS.items():
        if not apply_to(rel, spec, write=False):
            return 1
    if args.check:
        print("\nAll anchors matched. Re-run without --check to apply.")
        return 0
    print()
    for rel, spec in INSERTS.items():
        if not apply_to(rel, spec, write=True):
            return 1
    print("\nApplied. Next: run `make check`, then commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
