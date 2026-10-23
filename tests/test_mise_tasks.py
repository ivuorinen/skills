"""The mise file tasks under `.mise/tasks/` are the repository's gate.

They replaced the Makefile, so these tests hold what the Makefile's own tests
held: every task is runnable and listed, every former target still resolves,
`check` runs each gate in the phase it belongs to, and the pinned tools agree
with the lock CI installs from.
"""

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from mise_check import check_phases

ROOT = Path(__file__).parent.parent
TASKS = ROOT / ".mise" / "tasks"
READ_ONLY = [
    "validate",
    "validate-evals",
    "validate-rules",
    "ring-deps",
    "version-sync",
    "lock-check",
    "lint",
    "format-check",
    "security",
    "opengrep",
    "typecheck",
    "test",
    "bench",
    "agentlinter",
    "audit-consistency",
]
WRITERS = ["index-check", "prek"]
FORMER_TARGETS = {
    t: t
    for t in [
        *READ_ONLY,
        "index-check",
        "format",
        "list",
        "spec-check",
        "bench-recall",
        "agentlinter-update",
    ]
} | {"pre-commit": "prek", "bump-patch": "bump", "bump-minor": "bump", "bump-major": "bump"}
PINS = {
    "uv": "0.13.1",
    "ruff": "0.17.1",
    "npm:pyright": "1.1.414",
    "prek": "0.5.5",
    "opengrep": "1.27.1",
}
PLATFORMS = {"linux-x64", "macos-arm64", "macos-x64"}

_IN_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes")


def test_every_task_file_is_executable_and_described():
    """mise lists only executable files, and `mise tasks` shows the description.

    A task that loses its mode bit vanishes from `mise run` without an error,
    and one without a description is a blank row in the only list of targets.
    """
    files = [p for p in TASKS.iterdir() if p.is_file()]
    assert files
    for p in files:
        assert os.access(p, os.X_OK), p.name
        head = p.read_text(encoding="utf-8").splitlines()[:5]
        assert any(re.match(r'#\s*(\[MISE\]|MISE) description="[^"]+"', ln) for ln in head), p.name


def test_every_former_make_target_resolves_to_a_task():
    for target, task in FORMER_TARGETS.items():
        assert (TASKS / task).is_file(), f"make {target} has no task {task}"


def test_check_runs_every_gate_in_its_phase():
    assert check_phases(ROOT) == (READ_ONLY, WRITERS)


def test_check_continues_past_failures_and_serialises_writers():
    text = (TASKS / "check").read_text(encoding="utf-8")
    assert text.count("--continue-on-error") == 2
    assert "--jobs 1" in text
    assert "set -e" not in text.replace("set -uo pipefail", "")


def _stub_mise(tmp_path: Path, fail_first: bool) -> dict[str, str]:
    """Put a `mise` on PATH that logs its argv and fails the first call if asked."""
    log = tmp_path / "log"
    first = "exit 1" if fail_first else "exit 0"
    stub = tmp_path / "mise"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'log="{log}"\n'
        'seen=0; [ -f "$log" ] && seen=$(wc -l < "$log")\n'
        'printf "%s\\n" "$*" >> "$log"\n'
        f'[ "$seen" -eq 0 ] && {first}\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}


def test_check_runs_writers_after_a_failed_read_phase(tmp_path):
    """One run reports every failing gate, so a red read phase must not skip the writers."""
    env = _stub_mise(tmp_path, fail_first=True)
    r = subprocess.run(
        [str(TASKS / "check")], env=env, capture_output=True, text=True, cwd=ROOT, check=False
    )
    calls = (tmp_path / "log").read_text(encoding="utf-8").splitlines()
    assert r.returncode == 1
    assert len(calls) == 2
    assert "index-check" in calls[1]
    assert "prek" in calls[1]


def test_check_exits_0_when_every_gate_passes(tmp_path):
    env = _stub_mise(tmp_path, fail_first=False)
    r = subprocess.run(
        [str(TASKS / "check")], env=env, capture_output=True, text=True, cwd=ROOT, check=False
    )
    assert r.returncode == 0


def test_mise_toml_pins_exactly_the_spec_tools():
    """Tools only: `[env]`, `[settings]` or `[tasks]` would make the file need `mise trust`."""
    cfg = tomllib.loads((ROOT / "mise.toml").read_text(encoding="utf-8"))
    assert cfg == {"tools": PINS}


def test_mise_lock_carries_a_checksum_for_every_binary_tool_on_every_platform():
    """CI installs with MISE_LOCKED=1, so a platform missing here fails the job.

    Lockfile format 3 keys each platform as `"platforms.<platform>"`. An npm
    tool has no per-platform asset; its lock is a digest-pinned directory under
    `.mise/locks/`, which has to be committed beside `mise.lock`.
    """
    lock = tomllib.loads((ROOT / "mise.lock").read_text(encoding="utf-8"))
    for name, version in PINS.items():
        entries = lock["tools"][name]
        assert [e["version"] for e in entries] == [version]
        entry = entries[0]
        if name.startswith("npm:"):
            assert entry["aube"]["digest"].startswith("sha256:"), name
            assert (ROOT / entry["aube"]["path"]).is_dir(), name
            continue
        for p in PLATFORMS:
            assert entry.get(f"platforms.{p}", {}).get("checksum"), f"{name} {p}"


@pytest.mark.skipif(
    shutil.which("mise") is None and not _IN_CI,
    reason="mise is not installed; under CI a missing mise fails instead",
)
def test_tasks_run_from_the_repo_root():
    """Task bodies use repo-relative paths, so a run from a subdirectory must still work."""
    r = subprocess.run(
        ["mise", "run", "-q", "list"],
        cwd=ROOT / "skills",
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
