"""Every nitpicker command is pressure-tested, grandfathered, or fails this gate.

`.claude/rules/skill-lifecycle.md` says never skip a phase, and `/new-command`
makes RED and GREEN mandatory phases with exit artifacts — but nothing detected a
skipped one, so a command could ship having never been pressure-tested at all
(agent-loopholes, this session). This is the detector: a new command file must
arrive with a record in `pressure-records.json`, or be added to `grandfathered`,
which is a visible, reviewable line in a diff rather than a silent omission.

The registry is not a substitute for running the test. It records that one ran.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_COMMANDS = _REPO / "skills" / "nitpicker" / "commands"
_REGISTRY = _REPO / "skills" / "nitpicker" / "evals" / "pressure-records.json"
_VALIDATOR = _REPO / "scripts" / "validate-evals.py"


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(_REGISTRY.read_text(encoding="utf-8"))


def _command_stems() -> set[str]:
    """Dispatchable commands: `_`-prefixed files are shared references, not commands."""
    return {p.stem for p in _COMMANDS.glob("*.md") if not p.name.startswith("_")}


def _uncovered(registry: dict, stems: set[str]) -> list[str]:
    """Commands with neither a record nor a grandfather entry — what the gate rejects.

    A function of its inputs so the control below runs the gate's own arithmetic;
    a control that repeats the set subtraction inline passes whatever the gate does.
    """
    covered = set(registry["grandfathered"]) | {r["command"] for r in registry["records"]}
    return sorted(stems - covered)


def test_every_command_is_recorded_or_grandfathered(registry):
    missing = _uncovered(registry, _command_stems())
    assert not missing, (
        f"no pressure record for {', '.join(missing)} — run /skill-tester against the "
        "command and add a record, or add the name to 'grandfathered' so the omission "
        "is visible in review"
    )


def test_the_registry_names_no_command_that_does_not_exist(registry):
    """A renamed or deleted command must not leave a record behind claiming coverage."""
    named = set(registry["grandfathered"]) | {r["command"] for r in registry["records"]}
    stale = sorted(named - _command_stems())
    assert not stale, f"pressure-records.json names commands that do not exist: {stale}"


def test_the_registry_is_well_formed():
    """Fields, vocabularies, duplicates and exclusivity: validate-evals.py owns the
    shape, so the hook and pre-commit that run it hold the same bar this suite
    does (agent-loopholes-17e0386b). Checked here too, so a shape error also
    fails the unit run beside the coverage checks above."""
    spec = importlib.util.spec_from_file_location("validate_evals", _VALIDATOR)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    errors: list[str] = []
    module.validate_pressure_records(_REGISTRY, "nitpicker", errors)
    assert errors == []


def test_the_gate_can_fail():
    """Control: the coverage check must reject an unrecorded command, not just pass."""
    registry = {"grandfathered": ["gamma"], "records": [{"command": "alpha"}]}
    assert _uncovered(registry, {"alpha", "beta", "gamma"}) == ["beta"]
