#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Validate SKILL.md files for the ivuorinen-skills plugin.

Enforces the Agent Skills specification (https://agentskills.io/specification)
plus this repo's own stricter conventions. Where the two differ the repo rule is
the tighter one — the spec makes `description` free-form, we additionally
require a "Use when" trigger clause.

Usage: validate-skill.py [SKILL.md ...]

With no arguments, validates skills/*/SKILL.md and .claude/skills/*/SKILL.md.
`--help`/`-h` is answered before any argument is read as a path (audit-24b0f17a).

Exit codes: 0 valid, 1 validation errors, 2 usage error.
"""

import re
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import md_fences, parse_frontmatter

# Vendored skills — authored by someone else and installed into this repo (e.g.
# via `/graphify`), NOT held to our SKILL.md conventions. Skills named here are
# skipped by the validator (their descriptions, body length, etc. are their
# authors' concern, not ours).
#
# GOVERNANCE: this list is human-curated. It may contain ONLY vendored skills
# the repo owner has explicitly approved. An agent MUST NOT add an entry on its
# own — any skill not authored by us requires the owner's explicit confirmation
# before it goes here. `test_allowlist_contains_only_approved_entries` guards
# this; if it fails because of a new entry, that entry needs approval, not a
# test edit.
VENDORED_SKILLS: frozenset[str] = frozenset({"graphify"})

# Name Constraints (.claude/rules/skill-official-best-practices.md): lowercase
# letters, digits and hyphens only.
_NAME_RE = re.compile(r"^[a-z0-9-]+$")

# Frontmatter fields defined by https://agentskills.io/specification#frontmatter.
_SPEC_FIELDS: frozenset[str] = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)

# Top-level frontmatter key: unindented `key:` or `key: value`. YAML permits the
# key to be quoted, and a bare-word-only pattern silently skipped `"key": value`
# — the line then attached to the previous key as a nested line, so an
# unrecognised key escaped the spec-field check entirely. The bare spelling is any
# unindented run up to the first `:` for the same reason: a word-character class
# let `vendor.flag:` and `client setting:` through as nested lines
# (audit-70fd1d59).
_FM_KEY_RE = re.compile(r"""^(?:"([^"]*)"|'([^']*)'|([^\s#"'][^:]*?))[ \t]*:(.*)$""")

# A YAML flow collection opens with [ or {. The spec types `allowed-tools` as one
# space-separated string and `metadata` values as strings, so either marker in
# those positions is a type violation the reference validator also rejects.
_FLOW_RE = re.compile(r"^[\[{]")

# One `key: value` pair nested under a mapping field such as `metadata`. The key
# may be quoted — `"release channel": stable` is valid YAML the reference
# validator accepts, and a bare-word-only pattern rejected it as "not a
# 'key: value' pair". The `:` delimiter stays required: dropping it would let an
# empty value or a flow collection through the checks below.
_FM_NESTED_PAIR_RE = re.compile(
    r"""^[ \t]+(?:"([^"]*)"|'([^']*)'|([A-Za-z0-9_.-]+))[ \t]*:[ \t]*(.*)$"""
)


def filter_vendored(targets: list[Path]) -> tuple[list[Path], list[str]]:
    """Split SKILL.md targets into (validate, skipped-vendored-names).

    A target is vendored when its skill directory (the SKILL.md's parent) is
    named in VENDORED_SKILLS. Applies to both explicit args and auto-discovery,
    so an edited vendored SKILL.md is skipped rather than failing our checks.
    """
    kept: list[Path] = []
    skipped: list[str] = []
    for t in targets:
        if t.parent.name in VENDORED_SKILLS:
            skipped.append(t.parent.name)
        else:
            kept.append(t)
    return kept, skipped


def strip_fences(lines: list[str]) -> list[str]:
    """Return lines outside fenced code blocks.

    Handles indented fences, distinct markers (``` closed only by ```, ~~~ by
    ~~~), and the full delimiter length (a four-backtick opener is not closed by
    a three-backtick line). The open/close rule is the shipped `md_fences`, so
    this validator and the shipped tools cannot disagree about a fence.
    """
    result: list[str] = []
    fence = ""
    for line in lines:
        stripped = line.lstrip()
        if fence:
            if md_fences.closes(stripped, fence):
                fence = ""
            continue
        opened = md_fences.opener(stripped)
        if opened:
            fence = opened
            continue
        result.append(line)
    return result


# Shapes that are destructive, exfiltrating, or fetch-and-execute. Deliberately
# small: each is a thing no legitimate instruction block in this repo asks a
# reader to run, so a hit is a planted line rather than a style preference.
_UNSAFE_SHELL_RE = re.compile(
    # Fetch-and-execute, any shell, however the interpreter is spelled: a bare
    # name, an absolute path, or by way of `env` — including `env -i bash` and
    # `env VAR=x bash`, both ordinary idioms rather than obfuscation. Matching
    # the bare name alone let `| /bin/bash` past; allowing `env` but not its
    # options let `| env -i bash` past one round later.
    #
    # The token run between `env` and the shell is bounded and lazy. Bounded
    # because an unbounded repeat over `\S+` is the catastrophic-backtracking
    # shape opengrep flagged in this file's sibling check, and eight tokens is
    # far past any real invocation. Lazy because it must not swallow the shell
    # name it precedes, and because `env -u FOO zsh` puts a bare word in that
    # run — an option's argument, not an option.
    #
    # This is a heuristic over authored prose, not a security boundary: a
    # determined spelling will always evade it. It exists to catch a planted or
    # careless line in a file this repo ships.
    r"(?:curl|wget)[^|\n]*\|\s*"
    r"(?:\S*/)?"
    r"(?:env(?:\s+\S+){0,8}?\s+(?:\S*/)?)?"
    r"(?:ba|z|k|da)?sh\b"
    r"|rm\s+-rf\s+/(?:\s|$)"  # delete from root
    r"|chmod\s+777"
    r"|:\(\)\s*\{.*\|.*&\s*\}"  # fork bomb
    r"|>\s*/dev/sd[a-z]"  # write to a raw device
    r"|~/\.ssh|~/\.aws|id_rsa|/etc/shadow"  # credential material
    r"|eval\s+\"?\$\("  # eval of command substitution
)
# The languages whose blocks a reader copies and runs. A ```text or ```json
# block is illustration; a ```bash block is an instruction. Matched
# case-insensitively: a fence tag is written by hand, and ```Bash runs exactly
# like ```bash while a case-sensitive pattern reads it as prose.
_EXECUTABLE_FENCE_RE = re.compile(
    r"^(?:`{3,}|~{3,})\s*(bash|sh|shell|zsh|ksh|dash|console)\b", re.IGNORECASE
)


def unsafe_shell_lines(lines: list[str]) -> list[tuple[int, str]]:
    """(lineno, line) for dangerous commands inside *executable* fenced blocks.

    Scoped to shell fences on purpose, and the scoping is what makes the check
    usable here at all. This repo's shipped prose documents the defects it audits
    for — `iac.md` describes `curl | sh` as a Dockerfile finding, `prompt-safety.md`
    quotes "ignore prior instructions" as the attack string — so a scan over prose
    flags a security toolkit for containing security content. Measured on this
    repo: 10 hits across prose, all correct content; 0 inside the 19 blocks a
    reader is actually told to run.

    These files ship to consumers through `npx skills add`, and nothing else
    scans them — bandit and opengrep read `.py` only. A planted fetch-and-execute
    in a command file would reach every install.
    """
    out: list[tuple[int, str]] = []
    fence = ""
    executable = False
    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        if fence:
            if md_fences.closes(stripped, fence):
                fence = ""
                executable = False
            elif executable and _UNSAFE_SHELL_RE.search(line):
                out.append((i, line.strip()))
            continue
        opened = md_fences.opener(stripped)
        if opened:
            fence = opened
            executable = bool(_EXECUTABLE_FENCE_RE.match(stripped))
    return out


def _unterminated_fence(lines: list[str]) -> bool:
    """True if a fenced code block is opened but never closed.

    An unclosed fence makes strip_fences swallow the rest of the file, silently
    disabling every structural check below it — so this must fail validation,
    not pass unnoticed.
    """
    fence = ""
    for line in lines:
        stripped = line.lstrip()
        if fence:
            if md_fences.closes(stripped, fence):
                fence = ""
        else:
            fence = md_fences.opener(stripped) or fence
    return bool(fence)


def frontmatter_block(text: str) -> str:
    """The raw text between the opening and closing `---` lines, '' if absent.

    parse_frontmatter() flattens to `key: value` pairs and drops indented lines,
    so it cannot see the *shape* of `metadata` or a bare `allowed-tools:`. The
    spec constrains those shapes, so they are checked against the raw block.
    """
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return ""
    end = text.find("\n---\n", 4)
    return "" if end == -1 else text[4:end]


def _fm_sections(block: str) -> list[tuple[str, str, list[str]]]:
    """Split a frontmatter block into (key, inline_value, nested_lines) triples.

    Nested lines are the indented lines belonging to the preceding top-level key,
    which is how a mapping field such as `metadata` carries its entries.
    """
    sections: list[tuple[str, str, list[str]]] = []
    for line in block.splitlines():
        if not line.strip():
            continue
        m = _FM_KEY_RE.match(line)
        if m:
            # Groups 1-3 are the quoted and bare spellings of the key; exactly
            # one matches. Group 4 is the inline value.
            key = next(g for g in m.group(1, 2, 3) if g is not None)
            sections.append((key, m.group(4).strip(), []))
        elif sections:
            sections[-1][2].append(line)
    return sections


_BLOCK_INDICATORS = (">", "|", ">-", "|-", ">+", "|+")


def resolve_scalar(inline: str, nested: list[str]) -> str:
    """Resolve a YAML block scalar to its text; pass any plain value through.

    parse_frontmatter() splits on the first ': ' and drops indented lines, so a
    folded (`>`) or literal (`|`) value reads back as the indicator character
    itself. Validating that would judge `description: >` as the one-character
    string '>' — failing the 'Use when' check on a description that has it, and
    measuring 1 against the 1024-char limit. The spec's own guidance uses the
    folded form for long descriptions, so this shape has to resolve.

    `>` folds line breaks to spaces, `|` keeps them.
    """
    if inline not in _BLOCK_INDICATORS:
        return inline
    joiner = "\n" if inline[0] == "|" else " "
    return joiner.join(ln.strip() for ln in nested).strip()


def frontmatter_values(block: str) -> dict[str, str]:
    """Frontmatter scalars with block scalars resolved, keyed by field name."""
    return {key: resolve_scalar(inline, nested) for key, inline, nested in _fm_sections(block)}


def _check_compatibility(inline: str, nested: list[str], err: Callable[[str], None]) -> None:
    """`compatibility`: 1-500 characters when present."""
    value = resolve_scalar(inline, nested) or " ".join(ln.strip() for ln in nested)
    if not value:
        err("'compatibility' is present but empty; omit it or give it a value")
    elif len(value) > 500:
        err(f"compatibility is {len(value)} chars; must be ≤500")


def _check_metadata(inline: str, nested: list[str], err: Callable[[str], None]) -> None:
    """`metadata`: a mapping of string keys to string values."""
    if inline:
        err("'metadata' must be nested 'key: value' entries, not an inline value")
        return
    if not nested:
        err("'metadata' is present but has no entries; omit it or add entries")
    for ln in nested:
        pair = _FM_NESTED_PAIR_RE.match(ln)
        if not pair:
            err(f"'metadata' entry is not a 'key: value' pair: {ln.strip()!r}")
            continue
        # Groups 1-3 are the quoted and bare spellings of the key; group 4 is
        # the value.
        key = next(g for g in pair.group(1, 2, 3) if g is not None)
        value = pair.group(4)
        if not value:
            # A key with no scalar opens a nested map or list; values are strings.
            err(f"'metadata.{key}' must be a string, not a nested structure")
        elif _FLOW_RE.match(value):
            err(f"'metadata.{key}' must be a string, not a flow collection")


def _check_allowed_tools(inline: str, nested: list[str], err: Callable[[str], None]) -> None:
    """`allowed-tools`: one space-separated string."""
    if nested:
        err("'allowed-tools' must be a single space-separated string, not a list")
    elif not inline:
        err("'allowed-tools' is present but empty; omit it or list the tools")
    elif _FLOW_RE.match(inline):
        err("'allowed-tools' must be a single space-separated string, not a flow collection")


_FIELD_CHECKS: dict[str, Callable[[str, list[str], Callable[[str], None]], None]] = {
    "compatibility": _check_compatibility,
    "metadata": _check_metadata,
    "allowed-tools": _check_allowed_tools,
}


def validate_frontmatter_fields(block: str, err: Callable[[str], None]) -> None:
    """Check the optional spec fields the flat parser cannot see.

    https://agentskills.io/specification#frontmatter — `compatibility` is capped
    at 500 characters, `metadata` is a map of string keys to string values, and
    `allowed-tools` is a single space-separated string.

    A key outside the spec is an error, matching the reference validator: the
    spec routes client-specific properties into `metadata`, so a top-level
    client key is a portability bug, not a stylistic one.
    """
    for key, inline, nested in _fm_sections(block):
        if key not in _SPEC_FIELDS:
            err(
                f"frontmatter key '{key}' is not in the Agent Skills spec — "
                "move client-specific properties under 'metadata'"
            )
        check = _FIELD_CHECKS.get(key)
        if check:
            check(inline, nested, err)


def validate(path: Path, errors: list[str], warnings: list[str]) -> None:  # noqa: C901
    """Check one SKILL.md, appending to the caller's lists rather than returning.

    Accumulating across files lets a run report every problem in the tree at
    once, which is what an author fixing skills needs — one pass, not one error
    per attempt. Errors and warnings stay separate because only the first fails
    the gate: a body over the size guidance is worth saying and not worth
    blocking a commit over.
    """

    def err(msg: str) -> None:
        errors.append(f"  ERROR  {path}: {msg}")

    def warn(msg: str) -> None:
        warnings.append(f"  WARN   {path}: {msg}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        err(f"cannot read file: {e}")
        return

    text = text.replace("\r\n", "\n")  # normalize CRLF so frontmatter checks and slicing work

    if not text.startswith("---\n"):
        err("missing YAML frontmatter (file must start with ---)")
        return

    fm, body = parse_frontmatter(text)

    # parse_frontmatter() is flat and cannot see block scalars, so the
    # description is taken from the raw block instead — see resolve_scalar().
    block = frontmatter_block(text)
    values = frontmatter_values(block)

    name = fm.get("name", "")
    description = values.get("description", "") or fm.get("description", "")

    if not name:
        err("frontmatter missing 'name' field")
    if not description:
        err("frontmatter missing 'description' field")
    else:
        if "Use when" not in description:
            err("description must contain 'Use when' trigger clause")
        if len(description) > 1024:
            err(f"description is {len(description)} chars; must be ≤1024")

    end_fm = text.find("\n---\n", 4)
    for line in text[4:end_fm].splitlines():
        if line.startswith("description: "):
            raw_val = line[len("description: ") :].strip()
            is_quoted = len(raw_val) >= 2 and raw_val[0] == "'" and raw_val[-1] == "'"
            if ": " in raw_val and not is_quoted:
                err("description contains ': ' — wrap in single quotes (project convention)")
            break

    expected_name = path.parent.name
    if name and name != expected_name:
        err(f"name '{name}' does not match directory '{expected_name}'")

    # Name Constraints from .claude/rules/skill-official-best-practices.md. Vendored
    # skills are their authors' concern (same skip as filter_vendored applies).
    if name and path.parent.name not in VENDORED_SKILLS:
        if len(name) > 64:
            err(f"name is {len(name)} chars; must be ≤64")
        if not _NAME_RE.match(name):
            err(f"name '{name}' must contain only lowercase letters, digits and hyphens")
        # Agent Skills spec: no leading/trailing hyphen, no consecutive hyphens.
        if name.startswith("-") or name.endswith("-"):
            err(f"name '{name}' must not start or end with a hyphen")
        if "--" in name:
            err(f"name '{name}' must not contain consecutive hyphens")
        for reserved in ("anthropic", "claude"):
            if reserved in name.lower():
                err(f"name '{name}' contains reserved word '{reserved}'")

    validate_frontmatter_fields(block, err)

    # An unterminated fence makes every fence-aware check below go silent.
    if _unterminated_fence(body.splitlines()):
        err("unterminated code fence — every ``` or ~~~ must be closed")

    # `body` starts after the frontmatter, so a line number from it is
    # body-relative. Reported unadjusted it names a physical line that holds
    # something else entirely — and the reader trusts it, because every other
    # error in this file counts from line 1 of the file.
    body_offset = len(text.splitlines()) - len(body.splitlines())
    for lineno, snippet in unsafe_shell_lines(body.splitlines()):
        err(f"line {lineno + body_offset}: unsafe command in an executable block: {snippet[:80]}")

    # Header level progression — no skipping levels (ignores fenced code blocks)
    headers: list[tuple[int, str]] = []
    for line in strip_fences(body.splitlines()):
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            headers.append((level, line.lstrip("# ")))

    prev_level = 1  # body follows frontmatter; treat skill title (h1) as baseline
    for level, title in headers:
        if level > prev_level + 1:
            err(f"header level jumps from h{prev_level} to h{level}: '{'#' * level} {title}'")
        prev_level = level

    # Duplicate headers — the same heading must not appear twice (ignores fenced code blocks)
    seen_headers: set[tuple[int, str]] = set()
    for level, title in headers:
        key = (level, title.strip())
        if key in seen_headers:
            err(f"duplicate header: '{'#' * level} {title.strip()}'")
        seen_headers.add(key)

    # Body length — official best-practices recommend ≤500 lines for optimal performance
    body_lines = len(body.splitlines())
    if body_lines > 500:
        warn(
            f"SKILL.md body is {body_lines} lines; "
            "official best-practices recommend ≤500 — split into separate files"
        )

    # Progressive disclosure (https://agentskills.io/specification#progressive-disclosure):
    # the instructions tier should stay under ~5000 tokens. Estimated at 4 chars
    # per token — close enough to catch a body that has outgrown the tier, and it
    # needs no tokeniser dependency in a stdlib-only gate.
    est_tokens = len(body) // 4
    if est_tokens > 5000:
        warn(
            f"SKILL.md body is ~{est_tokens} tokens; progressive disclosure "
            "recommends <5000 — move reference material into separate files"
        )

    # Legacy output paths — scan prose and inline code, but skip fenced code blocks
    # (example/format documentation) and table rows (behavior documentation).
    # strip_fences, not a backtick regex: the regex paired runs across a nested
    # fence, dropped the prose between, and never saw ~~~ (audit-4562b342).
    body_no_doc = "\n".join(
        ln for ln in strip_fences(body.splitlines()) if not re.fullmatch(r"\|.*\|", ln)
    )
    for legacy in ("./codereview.md", "./fixreport.md", "codereview.md", "fixreport.md"):
        if legacy in body_no_doc:
            warn(f"references legacy output path '{legacy}' — use docs/audit/ instead")

    commands_dir = path.parent / "commands"
    if commands_dir.is_dir():
        validate_commands(commands_dir, name or expected_name, body, errors)
    else:
        table_cmds = table_commands(body)
        if table_cmds:
            err(f"Commands table lists {len(table_cmds)} commands but commands/ does not exist")


_CMD_ROW = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|")


_CMD_SECTIONS = frozenset({"Commands", "Internal commands"})
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def _command_table_rows(skill_body: str) -> list[tuple[str, str]]:
    """(command, stripped row) for each row under `## Commands` or `## Internal commands`.

    A section runs to the next heading of level 2 or higher, so its `###`
    subsections stay in it. Rows from any other table used to count, so a
    command dropped from the dispatch tables still passed the 1:1 sync
    (audit-5315131e).
    """
    rows: list[tuple[str, str]] = []
    in_section = False
    for line in strip_fences(skill_body.splitlines()):
        heading = _HEADING.match(line)
        if heading and len(heading.group(1)) <= 2:
            in_section = len(heading.group(1)) == 2 and heading.group(2) in _CMD_SECTIONS
            continue
        stripped = line.strip()
        m = _CMD_ROW.match(stripped)
        if in_section and m and m.group(1) != "command":
            rows.append((m.group(1), stripped))
    return rows


def table_commands(skill_body: str) -> set[str]:
    """Return command names listed in the SKILL.md command tables."""
    return {name for name, _ in _command_table_rows(skill_body)}


def _duplicate_table_commands(skill_body: str) -> list[str]:
    """Command names that appear in more than one Commands-table row.

    table_commands() dedupes into a set, so a command listed twice would
    otherwise pass the 1:1 sync check unflagged.
    """
    seen: set[str] = set()
    dups: list[str] = []
    for name, _ in _command_table_rows(skill_body):
        if name in seen and name not in dups:
            dups.append(name)
        seen.add(name)
    return dups


_ALIAS_DECL = re.compile(r"\(alias(?:es)?:\s*([^)]*)\)")
_BACKTICKED = re.compile(r"`([a-z0-9][a-z0-9-]*)`")


def table_aliases(skill_body: str) -> list[tuple[str, str]]:
    """(alias, command) for every alias declared in a Commands-table row.

    The router has no alias map in code: the dispatcher resolves an alias by
    reading these cells, so the cells *are* the dispatch table. That makes an
    alias colliding with a canonical command name, or claimed by two commands,
    a genuine ambiguity — the agent has no tiebreak to apply — rather than a
    cosmetic slip. Nothing else checks this half of the registry; the 1:1 file
    sync covers canonical names only.
    """
    found: list[tuple[str, str]] = []
    for name, stripped in _command_table_rows(skill_body):
        for decl in _ALIAS_DECL.findall(stripped):
            found.extend((alias, name) for alias in _BACKTICKED.findall(decl))
    return found


def _alias_errors(skill_md: Path, skill_body: str, table_cmds: set[str]) -> list[str]:
    errors: list[str] = []
    claimed: dict[str, str] = {}
    for alias, cmd in table_aliases(skill_body):
        if alias in table_cmds:
            errors.append(
                f"  ERROR  {skill_md}: `{alias}` is declared as an alias of `{cmd}` but is "
                "also a command in its own right — the dispatcher cannot resolve it"
            )
        elif alias == cmd:
            errors.append(f"  ERROR  {skill_md}: `{cmd}` is listed as an alias of itself")
        elif alias in claimed and claimed[alias] != cmd:
            errors.append(
                f"  ERROR  {skill_md}: alias `{alias}` is claimed by both "
                f"`{claimed[alias]}` and `{cmd}`"
            )
        elif alias in claimed:
            errors.append(f"  ERROR  {skill_md}: alias `{alias}` is listed twice for `{cmd}`")
        claimed.setdefault(alias, cmd)
    return errors


# Pattern rules the skill-consistency-enforcer agent applied differently from run
# to run on identical files (agent-rules-a40d97d1). Each has a textual answer, so
# a regex settles it the same way every time and the agent keeps only judgement.
#
# A bare `findings.py <subcommand>` does not resolve from the audited repo's root,
# and outside Claude Code the fallback is the only interface. A `/` before the
# name (`scripts/findings.py`, `${CLAUDE_SKILL_DIR}/scripts/findings.py`) passes;
# so does a quoted path, because the closing quote separates name and subcommand.
_BARE_FINDINGS_CLI = re.compile(
    r"(?<![/\w])findings\.py`?\s+"
    r"(?:new|resolve|list|show|validate|index|export|recheck|baseline|migrate|migrate-resolved)\b"
)
# The findings store accepts only these; a domain severity guide inventing a
# level describes findings that cannot be filed.
_SEVERITY_LEVELS = frozenset({"Critical", "High", "Medium", "Low", "Advisory"})
_SEVERITY_HEADER = re.compile(r"^\|\s*Severity\s*\|")
_FIRST_CELL = re.compile(r"^\|\s*([^|]*?)\s*\|")
# An override names a `_conventions.md` section by its bold title, before or after
# the file name in the same sentence. A title that is not a real `## ` heading
# leaves the override's boundary for the reader to guess.
_CONVENTIONS_SECTION_REF = re.compile(
    r"_conventions\.md`?\s+\*\*([^*]+)\*\*\s+section"
    r"|\*\*([^*]+)\*\*\s+section[^.]{0,80}?_conventions\.md"
)


def _conventions_headings(commands_dir: Path) -> set[str] | None:
    """The `## ` headings of the shared `_conventions.md`, or None when absent."""
    conv = commands_dir / "_conventions.md"
    try:
        lines = strip_fences(conv.read_text(encoding="utf-8").splitlines())
    except OSError:
        return None
    return {m.group(2) for ln in lines if (m := _HEADING.match(ln)) and len(m.group(1)) == 2}


def _bare_findings_cli_errors(text: str) -> list[str]:
    """One message per line calling `findings.py <subcommand>` without a path.

    Fenced blocks are scanned too: a Procedure step in a ```text fence is still an
    instruction the agent runs. A trailing `\\` joins the next line first, so
    `python3 findings.py \\` followed by `list` is one command, reported at the
    line it starts on.
    """
    commands: list[tuple[int, str]] = []
    pending, start = "", 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if not pending:
            start = lineno
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        commands.append((start, pending + line))
        pending = ""
    if pending:
        commands.append((start, pending))
    return [
        f"line {lineno}: bare `findings.py` call does not resolve outside the skill "
        'directory — use python3 "${CLAUDE_SKILL_DIR}/scripts/findings.py"'
        for lineno, command in commands
        if _BARE_FINDINGS_CLI.search(command)
    ]


def _severity_row_errors(content_lines: list[str]) -> list[str]:
    """One message per severity-table row naming a level the store does not accept."""
    msgs: list[str] = []
    in_table = False
    for line in content_lines:
        if _SEVERITY_HEADER.match(line):
            in_table = True
        elif not line.startswith("|"):
            in_table = False
        elif in_table and (m := _FIRST_CELL.match(line)):
            cell = m.group(1)
            # The `| --- |` separator row is all dashes and colons, not a level.
            if set(cell) - set("-: ") and cell not in _SEVERITY_LEVELS:
                msgs.append(
                    f"severity table row {cell!r} is not one of "
                    f"{', '.join(sorted(_SEVERITY_LEVELS))} (_conventions.md § Severity levels)"
                )
    return msgs


def _override_heading_errors(content_lines: list[str], headings: set[str]) -> list[str]:
    """One message per `_conventions.md` section reference whose title is no heading.

    Lines are joined into paragraphs first, because a reference wraps: triage.md
    puts the bold title on one line and `_conventions.md` on the next.
    """
    joined = " ".join(ln.strip() if ln.strip() else "\n" for ln in content_lines)
    msgs: list[str] = []
    for paragraph in joined.split("\n"):
        for m in _CONVENTIONS_SECTION_REF.finditer(paragraph):
            title = (m.group(1) or m.group(2)).strip()
            if title not in headings:
                msgs.append(
                    f"names a `_conventions.md` **{title}** section, but _conventions.md "
                    f"has no '## {title}' heading"
                )
    return msgs


def validate_commands(  # noqa: C901
    commands_dir: Path, skill_name: str, skill_body: str, errors: list[str]
) -> None:
    """Cross-check the SKILL.md Commands table against commands/*.md files."""

    table_cmds = table_commands(skill_body)
    errors.extend(_alias_errors(commands_dir.parent / "SKILL.md", skill_body, table_cmds))

    for dup in _duplicate_table_commands(skill_body):
        errors.append(
            f"  ERROR  {commands_dir.parent / 'SKILL.md'}: command `{dup}` "
            "appears in more than one Commands-table row"
        )

    # File Reference Depth (https://agentskills.io/specification#file-references):
    # every reference must be one level from SKILL.md. A shared `_`-prefixed file
    # that only a command names is reachable solely as SKILL.md -> command -> ref,
    # which is the forbidden chain — so SKILL.md must name it too.
    # Token match on the stem, not a bare substring: `_a` occurs inside
    # `_audit-coverage`, so a substring test would exempt an `_a.md` that
    # SKILL.md never names — the exact chain this check exists to reject. The
    # stem (not the filename) is matched because SKILL.md cites these files
    # both ways, as `_conventions.md` and as bare `_conventions`.
    #
    # Fenced blocks are stripped first: a name inside an example is not a live
    # instruction to load the file, so counting it would satisfy the rule while
    # the only real path to that reference still ran through a command.
    reference_text = "\n".join(strip_fences(skill_body.splitlines()))
    for ref in sorted(commands_dir.glob("_*.md")):
        if not re.search(rf"(?<![\w-]){re.escape(ref.stem)}(?![\w-])", reference_text):
            errors.append(
                f"  ERROR  {ref}: shared reference is not named in SKILL.md — "
                "reachable only through a command file, which chains references "
                "two levels deep"
            )

    file_cmds = {p.stem: p for p in sorted(commands_dir.glob("*.md")) if not p.name.startswith("_")}

    for cmd in sorted(table_cmds - set(file_cmds)):
        errors.append(
            f"  ERROR  {commands_dir.parent / 'SKILL.md'}: Commands table lists `{cmd}` "
            f"but no commands/{cmd}.md exists"
        )
    for cmd in sorted(set(file_cmds) - table_cmds):
        errors.append(f"  ERROR  {file_cmds[cmd]}: not in the Commands table of SKILL.md")

    headings = _conventions_headings(commands_dir)

    for cmd, cpath in file_cmds.items():

        def cerr(msg: str, cpath: Path = cpath) -> None:
            errors.append(f"  ERROR  {cpath}: {msg}")

        try:
            text = cpath.read_text(encoding="utf-8")
        except OSError as e:
            cerr(f"cannot read file: {e}")
            continue

        if text.startswith("---\n"):
            cerr("command files must not have YAML frontmatter (only the router SKILL.md does)")

        if _unterminated_fence(text.splitlines()):
            cerr("unterminated code fence — every ``` or ~~~ must be closed")

        for lineno, snippet in unsafe_shell_lines(text.splitlines()):
            cerr(f"line {lineno}: unsafe command in an executable block: {snippet[:80]}")

        # All structural checks ignore fenced code blocks.
        content_lines = strip_fences(text.splitlines())

        first_header = next((ln for ln in content_lines if ln.startswith("#")), "")
        expected_h1 = f"# /{skill_name} {cmd} — "
        if not (first_header.startswith(expected_h1) and first_header[len(expected_h1) :].strip()):
            cerr(f"h1 must be '# /{skill_name} {cmd} — <Title>' (found {first_header!r})")

        h1_count = sum(1 for ln in content_lines if ln.startswith("#") and not ln.startswith("##"))
        if h1_count > 1:
            cerr(f"command file has {h1_count} h1 headers; exactly one allowed")

        if not any(ln.rstrip() == "## When to use" for ln in content_lines):
            cerr("missing '## When to use' section")

        prev_level = 0
        for line in content_lines:
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                if prev_level and level > prev_level + 1:
                    cerr(f"header level jumps from h{prev_level} to h{level}: {line!r}")
                prev_level = level

        # `${CLAUDE_SKILL_DIR}` is set by Claude Code alone; elsewhere it expands to
        # nothing and the call becomes `python3 /scripts/<tool>.py`. Whether the file
        # says what the path resolves against is textual, so it is gated here rather
        # than left to a reading agent (agent-rules-a40d97d1).
        if "${CLAUDE_SKILL_DIR}" in text and not re.search("non-claude", text, re.IGNORECASE):
            cerr(
                "calls ${CLAUDE_SKILL_DIR} but carries no note for non-Claude agents — "
                "say the path resolves relative to this skill's directory"
            )

        for msg in _bare_findings_cli_errors(text) + _severity_row_errors(content_lines):
            cerr(msg)
        if headings is not None:
            for msg in _override_heading_errors(content_lines, headings):
                cerr(msg)


def _path_args(args: list[str]) -> list[Path]:
    """The SKILL.md paths named on the command line, after `--help` and options.

    Answered before any argument becomes a path, so `--help` is never reported
    as an unreadable file (audit-24b0f17a).
    """
    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)
    unknown = [a for a in args if a.startswith("-")]
    if unknown:
        print(f"error: unknown option {unknown[0]!r}", file=sys.stderr)
        print("usage: validate-skill.py [SKILL.md ...]", file=sys.stderr)
        sys.exit(2)
    return [Path(a) for a in args]


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    targets = _path_args(sys.argv[1:])

    if not targets:
        repo_root = Path(__file__).parent.parent
        targets = sorted(
            [*repo_root.glob("skills/*/SKILL.md"), *repo_root.glob(".claude/skills/*/SKILL.md")]
        )

    targets, skipped = filter_vendored(targets)
    for name in skipped:
        print(f"  SKIP   {name} (vendored — not authored by us, not validated)")

    if not targets:
        if not skipped:
            print("No SKILL.md files found.")
        sys.exit(0)

    for t in targets:
        validate(t, errors, warnings)

    if warnings:
        for w in warnings:
            print(w)

    if errors:
        for e in errors:
            print(e)
        print(f"\n{len(errors)} error(s). Fix before committing.")
        sys.exit(1)

    print(f"OK  {len(targets)} skill(s) validated.")


if __name__ == "__main__":
    main()
