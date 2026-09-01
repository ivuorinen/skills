"""Tests for skills/nitpicker/scripts/skill_catalog.py."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "skill_catalog",
    Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "skill_catalog.py",
)
sc = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(sc)  # type: ignore[union-attr]


def test_plugin_root_is_repo_root():
    # skill_catalog.py lives at <root>/skills/nitpicker/scripts/, so parents[3] is <root>.
    assert (sc.plugin_root() / "skills" / "nitpicker" / "SKILL.md").is_file()


def test_list_skills_includes_nitpicker_with_commands():
    skills = sc.list_skills()
    names = {s["name"] for s in skills}
    assert "nitpicker" in names
    nit = next(s for s in skills if s["name"] == "nitpicker")
    assert nit["description"]
    assert "review" in nit["commands"]


def test_list_skills_lists_nitpicker_once():
    names = [s["name"] for s in sc.list_skills()]
    assert names.count("nitpicker") == 1


def test_list_skills_excludes_the_internal_dot_claude_tier():
    # `.claude/skills/` is the internal dev tier here and the user's own private
    # skill directory on a consumer machine — never part of what this tool reads.
    assert all(s["path"].startswith("skills/") for s in sc.list_skills())


def test_list_skills_attaches_commands_only_to_nitpicker(tmp_path):
    """Every other skill must come back without a `commands` key — attaching it
    everywhere would advertise a command surface those skills do not have."""
    from pathlib import Path

    for name, desc in (("nitpicker", "Audits."), ("other-skill", "Does not dispatch.")):
        d = tmp_path / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n\nBody.\n", encoding="utf-8"
        )
    cmds = tmp_path / "skills" / "nitpicker" / "commands"
    cmds.mkdir()
    (cmds / "review.md").write_text("# /nitpicker review — R\n\nP.\n", encoding="utf-8")
    (tmp_path / "skills" / "nitpicker" / "SKILL.md").write_text(
        "---\nname: nitpicker\ndescription: Audits.\n---\n\n## Commands\n\n"
        "| Command | Purpose |\n| --- | --- |\n| `review` | Hostile review |\n",
        encoding="utf-8",
    )

    by_name = {s["name"]: s for s in sc.list_skills(root=Path(tmp_path))}
    assert "commands" in by_name["nitpicker"]
    assert "commands" not in by_name["other-skill"]


def test_read_skill_returns_frontmatter_text():
    text = sc.read_skill("nitpicker")
    assert "name: nitpicker" in text


def test_read_skill_unknown_raises():
    import pytest

    with pytest.raises(KeyError, match="does-not-exist"):
        sc.read_skill("does-not-exist")


def test_list_commands_parses_name_alias_purpose():
    cmds = sc.list_commands()
    by_name = {c["name"]: c for c in cmds}
    assert "review" in by_name
    assert "adversarial-reviewer" in by_name["review"]["aliases"]
    assert by_name["review"]["purpose"]


def test_list_commands_tags_each_row_with_its_heading():
    """The `###` group is the category; a table with no group falls back to its `##`.

    That fallback is what keeps the internal table distinguishable — `help` and
    `triage` both need "public commands only", and before the category existed the
    only way to get it was to hardcode the internal command's name.
    """
    by_name = {c["name"]: c["category"] for c in sc.list_commands()}
    assert by_name["review"] == "Review and fixing"
    assert by_name["plan"] == "Planning"
    assert by_name["x-findings-migrator"] == "Internal commands"


def test_list_commands_filters_by_category_in_any_spelling():
    prose = sc.list_commands(category="Security and data")
    assert [c["name"] for c in prose] == sc_security_names()
    assert sc.list_commands(category="security-and-data") == prose
    assert sc.list_commands(category="SECURITY AND DATA") == prose


def sc_security_names():
    """The Security-and-data rows, read straight from SKILL.md rather than pinned.

    Hardcoding the five names here would make this test fail on any future
    addition to that category — a maintenance tax that proves nothing about
    filtering.
    """
    body = (sc.plugin_root() / "skills" / "nitpicker" / "SKILL.md").read_text(encoding="utf-8")
    section = body.split("### Security and data")[1].split("###")[0]
    return [c["name"] for c in sc.list_commands() if f"`{c['name']}`" in section]


def test_list_commands_rejects_an_unknown_category():
    """An empty list would read as "that category is empty", hiding the typo."""
    import pytest

    with pytest.raises(ValueError, match="unknown category 'planing'"):
        sc.list_commands(category="planing")
    with pytest.raises(ValueError, match="Review and fixing"):
        sc.list_commands(category="planing")


def test_read_command_known_and_traversal_rejected(monkeypatch):
    """The rejection must happen *before* any read.

    A bare `pytest.raises(KeyError)` cannot tell an allowlist rejection from an
    ordinary unknown-name lookup, and would still pass if the implementation
    became read-then-validate — by which point the traversal has already read the
    file. Failing the test on any read of the rejected path pins the ordering.
    """
    import re
    from pathlib import Path

    import pytest

    assert "# /nitpicker review" in sc.read_command("review")

    real_read_text = Path.read_text
    reads: list[str] = []

    def _recording_read_text(self, *a, **k):
        reads.append(str(self))
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _recording_read_text)

    for rejected in ("../../../../etc/passwd", "_conventions"):
        reads.clear()
        with pytest.raises(KeyError, match=re.escape(rejected)):
            sc.read_command(rejected)
        assert not any("passwd" in r or r.endswith("_conventions.md") for r in reads), (
            f"read_command({rejected!r}) touched the file before rejecting it"
        )


def test_read_reference_serves_the_shared_files_in_both_spellings():
    """`read_command` refuses these names, so the router needs its own reader.

    The underscore is optional because prose cites the file (`_conventions.md`)
    and a reader cites the section (`conventions`); a tool that accepted only one
    spelling would fail half the calls it exists to serve.
    """
    underscored = sc.read_reference("_conventions")
    assert "# Shared Conventions" in underscored
    assert sc.read_reference("conventions") == underscored
    assert "## How audit uses this file" in sc.read_reference("audit-coverage")
    # The third file resolved from the day it landed but no test named it, so a
    # narrowing of the `_*.md` glob to an allowlist would have dropped it silently.
    assert sc.read_reference("teach-formats") == sc.read_reference("_teach-formats")


def test_read_reference_description_names_every_shared_file():
    """The tool description is the only surface a model picks `np_read_reference` from.

    It can carry a literal list, so it drifts from `commands/_*.md` the moment a
    shared file is added — and it did: it named two of three, leaving
    `_teach-formats` reachable but invisible, so `teach` read it off disk instead.
    Pinning the description against the filesystem fails that commit instead.
    """
    import re
    from pathlib import Path

    root = sc.plugin_root()
    on_disk = {p.stem.lstrip("_") for p in (root / "skills/nitpicker/commands").glob("_*.md")}
    described = (
        Path(root / "skills/nitpicker/scripts/mcp_server.py")
        .read_text(encoding="utf-8")
        .split('"np_read_reference"')[1]
        .split("def ")[0]
    )
    missing = {n for n in on_disk if not re.search(rf"\b_?{re.escape(n)}\b", described)}
    assert not missing, f"np_read_reference's description does not name: {sorted(missing)}"


def test_read_reference_resolves_a_scanner_reference():
    """`references/tools/*.md` had no MCP route at all when it was introduced.

    The tool-preference rule ranks a raw filesystem read last for "any command
    file, shared reference, or this router", and these are shared references by
    that description — so every other bundled text had a tool and these did not.
    """
    body = sc.read_reference("codeql")
    assert "codeql" in body.lower()
    # The underscore is optional here exactly as it is for a command reference.
    assert sc.read_reference("_codeql") == body


def test_every_scanner_reference_is_reachable_by_name():
    """One file left unreachable is the `_teach-formats` failure again: present,
    resolvable in principle, and invisible to the caller."""
    root = sc.plugin_root()
    for path in sorted((root / "skills/nitpicker/references/tools").glob("*.md")):
        assert sc.read_reference(path.stem), f"{path.stem} did not resolve"


def test_a_command_reference_wins_a_name_collision():
    """`commands/_*.md` is the older contract, so a new scanner file sharing a
    stem must not change what an existing caller already resolves."""
    import pathlib as _p

    root = sc.plugin_root()
    clash = root / "skills/nitpicker/references/tools/conventions.md"
    clash.write_text("# not the conventions file\n", encoding="utf-8")
    try:
        assert "Shared Conventions" in sc.read_reference("conventions")
    finally:
        _p.Path(clash).unlink()


def test_unknown_reference_names_both_roots():
    """The error is the caller's only vocabulary, so it must list what is
    reachable — including the scanner references, or they stay invisible."""
    import pytest as _pytest

    with _pytest.raises(KeyError) as exc:
        sc.read_reference("no-such-reference")
    msg = str(exc.value)
    assert "conventions" in msg and "codeql" in msg


def _skill_body_outside_fences() -> str:
    """The nitpicker router's text with fenced blocks removed.

    Reuses the validator's own `strip_fences` rather than reimplementing it, so
    the two cannot disagree about what counts as a live mention. A name inside a
    fence is an example, not an instruction to load the file.
    """
    import importlib.util

    root = sc.plugin_root()
    spec = importlib.util.spec_from_file_location(
        "validate_skill", root / "scripts" / "validate-skill.py"
    )
    vs = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(vs)  # type: ignore[union-attr]
    body = (root / "skills/nitpicker/SKILL.md").read_text(encoding="utf-8")
    return "\n".join(vs.strip_fences(body.splitlines()))


def test_skill_md_names_every_external_scanner_reference():
    """`references/tools/*.md` sits outside every gate that gets this for free.

    `validate-skill.py` enforces the same rule for `commands/_*.md` and globs
    only that directory, so these files are reachable, unnamed, and invisible to
    the validator all at once — the shape that already shipped once as
    `_teach-formats`, which resolved from the day it landed while nothing named
    it. Without this test a tenth scanner added under `references/tools/` never
    gets mentioned in SKILL.md and is found only by whoever goes looking.
    """
    import re

    root = sc.plugin_root()
    on_disk = {p.stem for p in (root / "skills/nitpicker/references/tools").glob("*.md")}
    assert on_disk, "no scanner reference files found — the glob or the directory moved"

    named = _skill_body_outside_fences()
    missing = {n for n in on_disk if not re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", named)}
    assert not missing, f"SKILL.md does not name these scanner references: {sorted(missing)}"


def test_every_cited_scanner_reference_resolves():
    """The reverse drift: a routing row pointing at a file that is not there.

    `security.md`'s table is what an agent follows after detection, so a stale
    row sends it to a missing file mid-run. Checked across every command file
    rather than just that one, since any command may cite a scanner later.
    """
    import re

    root = sc.plugin_root()
    tools_dir = root / "skills/nitpicker/references/tools"
    dangling: list[str] = []
    for md in sorted((root / "skills/nitpicker/commands").glob("*.md")):
        text = md.read_text(encoding="utf-8")
        for cited in re.findall(r"references/tools/([\w-]+)\.md", text):
            if not (tools_dir / f"{cited}.md").is_file():
                dangling.append(f"{md.name} -> references/tools/{cited}.md")
    assert not dangling, f"cited scanner reference files do not exist: {dangling}"


def test_unknown_name_errors_name_the_valid_set():
    """A bare `KeyError(name)` renders as `KeyError: 'loopholes'` — no recovery path.

    `loopholes` is a SKILL.md-declared alias, not a typo, and these resolvers take
    canonical names only. Without the vocabulary in the message an agent reads the
    tool as dead and falls back to reading the file off disk, which is the
    fallback these readers exist to remove.
    """
    import pytest

    with pytest.raises(KeyError, match="agent-loopholes"):
        sc.read_command("loopholes")
    with pytest.raises(KeyError, match="teach-formats"):
        sc.read_reference("no-such-reference")
    with pytest.raises(KeyError, match="nitpicker"):
        sc.read_skill("no-such-skill")


def test_read_reference_rejects_non_reference_names_before_reading(monkeypatch):
    """Public commands and traversal both miss the enumerated set — no path is built.

    Same ordering guarantee `read_command` carries: rejection precedes any read,
    so a future read-then-validate rewrite fails here instead of shipping.
    """
    import re
    from pathlib import Path

    import pytest

    real_read_text = Path.read_text
    reads: list[str] = []

    def _recording_read_text(self, *a, **k):
        reads.append(str(self))
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _recording_read_text)

    for rejected in ("review", "../../../../etc/passwd"):
        reads.clear()
        with pytest.raises(KeyError, match=re.escape(rejected)):
            sc.read_reference(rejected)
        assert not reads, f"read_reference({rejected!r}) read a file before rejecting it"
