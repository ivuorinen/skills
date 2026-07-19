#!/usr/bin/env python3
"""Manage the per-finding audit store under docs/audit/findings/.

Ships inside the nitpicker skill: stdlib-only, Python 3.11+, no uv required.

Layout:
    docs/audit/findings/<auditor>/open/<id>.md   one open finding per file
    docs/audit/findings/resolved.jsonl           append-only ledger of resolved
                                                 findings (one JSON object/line)
    docs/audit/findings/INDEX.md                 generated; never hand-edited
    docs/audit/findings/.gitattributes           generated; marks the store
                                                 linguist-generated so audit runs
                                                 do not flood PR diffs

Open findings are files (few at a time, git-diffable, reviewable). Resolving a
finding appends a record to resolved.jsonl and deletes the open file, so the
tree never accumulates hundreds of resolved files. IDs are content-hashed
(`<auditor>-<8 hex>` of auditor+area+title) so parallel worktrees never race on
a counter; legacy `N-42`-style IDs from migrated v1 files stay valid.

Subcommands:
    new              create an open finding
    resolve          mark a finding fixed/invalid (moves it to the ledger)
    list             list findings (open files + resolved ledger)
    show             print one finding (open file or resolved ledger)
    validate         structural validation (exit 1 on errors)
    index            regenerate INDEX.md
    migrate          convert a v1 *-findings.md document into the store
    migrate-resolved (legacy 1.x store layout only) convert legacy
                     <auditor>/resolved/*.md files into the ledger
"""

import argparse
import contextlib
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path("docs/audit/findings")
LEDGER_NAME = "resolved.jsonl"
BASELINE_NAME = "baseline.json"
SEVERITIES = ("critical", "high", "medium", "low", "advisory")
CATEGORIES = (
    "correctness",
    "security",
    "reliability",
    "maintainability",
    "performance",
    "tests",
    "docs",
    "conventions",
)
STATUSES = ("open", "fixed", "invalid")
OPEN_SECTIONS = ("Problem", "Evidence", "Impact", "Fix")

_LEGACY_ID = re.compile(r"^[A-Z]+-\d+$")
_HASH_ID = re.compile(r"^[a-z0-9][a-z0-9-]*-[0-9a-f]{8}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_AUDITOR = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# Frontmatter keys with a dedicated column; anything else is preserved under
# the ledger record's "extra" object (e.g. cve:).
_KNOWN_FM = ("id", "auditor", "severity", "category", "area", "status", "found", "resolved")

# Redaction at the write choke point. _conventions.md binds every command to
# redact credentials and personal data from finding evidence, but a convention
# in a markdown file only binds a model that read it — the MCP tools, a manual
# `findings.py new`, and any subagent that skipped _conventions.md all reach
# this same writer. Resolution appends to an append-only ledger, so a secret
# written here is permanent, and the store's linguist-generated mark collapses
# these files in PR diffs, removing the review that would catch it.
_SECRET_RE = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}"
    r"|sk-[A-Za-z0-9-]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"
)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")


def _mask(token: str) -> str:
    # Cite the file:line in the finding; the location stays retrievable from the
    # source, so the record never needs to carry the value itself.
    return f"{token[:4]}***{token[-4:]}" if len(token) > 8 else "[REDACTED]"


def redact(text: str) -> str:
    """Strip credentials and email addresses from text bound for the store."""
    text = _SECRET_RE.sub(lambda m: _mask(m.group()), text)
    return _EMAIL_RE.sub("<email>", text)


# In-store .gitattributes: written by findings.py in its own domain so it never
# edits the repo-root .gitattributes. Patterns are relative to this dir.
_STORE_GITATTRIBUTES = ".gitattributes"
_GITATTR_MARK = "linguist-generated"
_STORE_GITATTRIBUTES_BODY = (
    "# Managed by findings.py (the nitpicker findings store). Patterns here are\n"
    "# relative to this directory, so this marks the whole findings store as a\n"
    '# generated artifact: GitHub collapses these files in PR diffs ("load diff" on\n'
    "# demand) so audit runs don't flood review. Kept inside the store so the skill\n"
    "# never edits the repo-root .gitattributes. Delete this file only if the store\n"
    "# is gitignored. `findings.py validate` warns if neither this mark nor a\n"
    "# gitignore of the folder is present.\n"
    "** linguist-generated=true\n"
)

# v1 (single-document) format patterns, inherited from check-audit-consistency.py
_V1_FINDING = re.compile(r"^####\s+\[([A-Za-z0-9-]+)\]\s*(.*)$")
_V1_PASS = re.compile(r"^###\s+Pass\s+(\d+)\s+—\s+(\d{4}-\d{2}-\d{2})\s*$")
_V1_FIELD = re.compile(r"^(Category|Area|Problem|Evidence|Impact|Fix|Fixed|Notes):\s*(.*)$")
_V1_GENERATED = re.compile(r"^Generated:\s*(\d{4}-\d{2}-\d{2})")

# old skill name -> command/auditor key (2.0 vocabulary)
V1_AUDITOR_MAP = {
    "nitpicker": "audit",
    "arch": "arch",
    "arch-auditor": "arch",
    "arch-detector": "arch",
    "doc": "docs",
    "doc-auditor": "docs",
    "security": "security",
    "security-auditor": "security",
    "claude-rules-auditor": "agent-rules",
    "rules": "agent-rules",
    "adversarial-reviewer": "review",
    "pr-reviewer": "pr",
    "cr-implementer": "cr",
    "test-auditor": "tests",
    "perf-auditor": "perf",
    "dep-auditor": "deps",
    "silent-failure-hunter": "errors",
    "ci-auditor": "ci",
    "commit-auditor": "commits",
    "migration-auditor": "migrations",
    "observability-auditor": "observability",
    "api-contract-auditor": "contract",
    "a11y-auditor": "a11y",
    "data-privacy-auditor": "privacy",
    "config-auditor": "config",
    "resource-leak-auditor": "leaks",
    "i18n-auditor": "i18n",
    "concurrency-auditor": "concurrency",
    "loophole-hunter": "agent-loopholes",
    "loopholes": "agent-loopholes",
    "hooks-enforcer": "agent-hooks",
    "hooks": "agent-hooks",
    "complexity-hunter": "complexity",
}


class FindingError(Exception):
    """A finding operation failed (unknown id, malformed file, ...)."""


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse simple YAML frontmatter. Returns (dict, body); ({}, text) if absent.

    The single implementation: scripts/common.py re-exports this one, so the
    shipped tool and the internal validators cannot drift apart. The dependency
    points internal -> shipped, the only safe direction (shipped tools ship
    without scripts/).
    """
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm: dict[str, str] = {}
    for line in text[4:end].splitlines():
        # Indented lines are nested values, not top-level keys. Without this,
        # an accidentally-indented `name:` parses as a real key here while
        # check-rules-anatomy's parser drops it — the two validators then
        # disagree about whether the same file has a name.
        if ": " in line and not line.startswith((" ", "\t")):
            k, _, v = line.partition(": ")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            fm[k.strip()] = v
    return fm, text[end + 5 :]


def _today() -> str:
    # UTC, not local: the same resolve run on a developer's machine and on a CI
    # runner must record the same date, or the ledger is quietly non-monotonic.
    return datetime.datetime.now(datetime.UTC).date().isoformat()


def _check_auditor(auditor: str) -> None:
    """Reject auditor keys that are not plain kebab-case (they become path parts)."""
    if not _AUDITOR.match(auditor):
        raise FindingError(f"invalid auditor {auditor!r}: want lowercase kebab-case")


def _check_id(fid: str) -> None:
    if not (_LEGACY_ID.match(fid) or _HASH_ID.match(fid)):
        raise FindingError(f"malformed finding id {fid!r}")


def finding_id(auditor: str, area: str, title: str) -> str:
    # 32 bits per auditor namespace puts the birthday-collision ceiling around
    # 77k findings for one auditor — far past any real audit volume, and a
    # collision is rejected by `new_finding` rather than overwriting. Widening
    # the slice would rewrite every existing id, so the width is fixed.
    digest = hashlib.sha256(f"{auditor}\0{area}\0{title}".encode()).hexdigest()
    return f"{auditor}-{digest[:8]}"


def v1_auditor(filename: str) -> str:
    stem = filename.removesuffix(".md").removesuffix("-findings")
    return V1_AUDITOR_MAP.get(stem, stem)


def _normalize_body(body: str) -> str:
    """Make a body markdownlint-clean outside code fences: blank lines around
    headings, blank-line runs collapsed. Fenced content is preserved verbatim,
    and a fence only closes on the marker that opened it (``` vs ~~~)."""
    out: list[str] = []
    fence = ""  # opening marker while inside a fence, else ""
    for line in body.strip().splitlines():
        stripped = line.rstrip()
        marker = stripped[:3] if stripped.startswith(("```", "~~~")) else ""
        if fence:
            out.append(line)
            if marker == fence:
                fence = ""
        elif marker:
            fence = marker
            out.append(line)
        elif not stripped:
            if out and out[-1].strip():
                out.append("")
        elif stripped.startswith("#"):
            if out and out[-1].strip():
                out.append("")
            out.append(stripped)
            out.append("")
        else:
            out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def _strip_fenced(body: str) -> str:
    """Return the body with fenced code regions removed, so structural checks
    (e.g. required-section headings) never match a heading inside a ``` block.
    A fence closes only on the marker that opened it (``` vs ~~~)."""
    out: list[str] = []
    fence = ""
    for line in body.splitlines():
        stripped = line.rstrip()
        marker = stripped[:3] if stripped.startswith(("```", "~~~")) else ""
        if fence:
            if marker == fence:
                fence = ""
            continue
        if marker:
            fence = marker
            continue
        out.append(line)
    return "\n".join(out)


def _drop_trailing_resolution(body: str) -> str:
    """Remove a trailing '## Resolution' section so a --force re-resolve replaces
    it instead of appending a duplicate. resolve_finding always appends the
    resolution as the last section, so truncating from the last '## Resolution'
    heading is exact."""
    lines = body.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].rstrip() == "## Resolution":
            return "\n".join(lines[:i]).rstrip()
    return body


def _render_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a markdown table padded to per-column content width (the same
    shape prettier produces, so auto-formatters leave it untouched)."""
    widths = [
        max(3, len(h), *(len(r[i]) for r in rows)) if rows else max(3, len(h))
        for i, h in enumerate(headers)
    ]

    def fmt(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True)) + " |"

    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    return [fmt(headers), sep, *(fmt(r) for r in rows)]


def render_finding(fm: dict[str, str], title: str, body: str) -> str:
    if "\n" in title:
        raise FindingError("title must be single-line")
    lines = ["---"]
    # Known keys in canonical order, then any extra keys (e.g. cve:) preserved.
    for key in (*_KNOWN_FM, *(k for k in fm if k not in _KNOWN_FM)):
        value = fm.get(key, "")
        if "\n" in value:
            # A newline would inject extra frontmatter lines (last-write-wins on parse).
            raise FindingError(f"frontmatter field {key!r} must be single-line")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            # parse_frontmatter strips one matching quote pair, so a pre-quoted
            # value would not round-trip: the stored `area` would differ from the
            # one that produced the content-hashed id, and an identical re-file
            # would be rejected as a phantom hash collision.
            raise FindingError(
                f"frontmatter field {key!r} must not be wrapped in quotes "
                "(the parser strips them, so the value would not round-trip)"
            )
        if value:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(_normalize_body(body))
    return "\n".join(lines) + "\n"


def parse_finding(text: str) -> tuple[dict[str, str], str, str]:
    """Return (frontmatter, title, body-after-title)."""
    fm, body = parse_frontmatter(text)
    title = ""
    rest: list[str] = []
    for line in body.splitlines():
        if not title and line.startswith("# "):
            title = line[2:].strip()
            continue
        rest.append(line)
    return fm, title, "\n".join(rest).strip() + "\n"


# ── resolved-findings ledger (docs/audit/findings/resolved.jsonl) ─────────────


def ledger_path(root: Path) -> Path:
    return root / LEDGER_NAME


# The store has three independent writers — the CLI, the MCP server, and the
# PostToolUse hook — so every read-modify-write below must be exclusive. Without
# it, two concurrent resolves each rewrite the ledger from the same snapshot and
# the second silently drops the first's record, while both delete their open file.
try:
    import fcntl
except ImportError:  # pragma: no cover — non-POSIX
    fcntl = None  # type: ignore[assignment]


@contextlib.contextmanager
def store_lock(root: Path):
    """Hold an exclusive lock on the store for the duration of the block.

    ponytail: flock only, no Windows path. On a platform without fcntl this
    degrades to no locking — single-writer use stays correct, concurrent use
    reverts to the pre-lock races. Add msvcrt.locking if Windows ever matters.
    """
    if fcntl is None:  # pragma: no cover — non-POSIX
        yield
        return
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def read_ledger(root: Path, errors: list[str] | None = None) -> list[dict]:
    """Parse resolved.jsonl into a list of records; malformed lines go to
    `errors` (or stderr) instead of crashing."""
    p = ledger_path(root)
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as e:
        _note(errors, f"{p}: cannot read: {e}")
        return []
    recs: list[dict] = []
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            rec = json.loads(s)
        except json.JSONDecodeError as e:
            _note(errors, f"{p}:{i}: invalid JSON: {e}")
            continue
        if not isinstance(rec, dict):
            _note(errors, f"{p}:{i}: ledger line is not a JSON object")
            continue
        recs.append(rec)
    return recs


def resolved_records(root: Path) -> dict[str, dict]:
    """Ledger records keyed by id; a re-resolved id keeps its last line."""
    by_id: dict[str, dict] = {}
    for rec in read_ledger(root):
        rid = rec.get("id")
        if rid:
            by_id[rid] = rec
    return by_id


def _ledger_summary(root: Path) -> dict[str, tuple[str, str]]:
    """id -> (auditor, status), streamed a line at a time.

    The index only needs these two fields, but every record embeds the finding's
    whole body. Reading the file by line and keeping two short strings per id
    caps peak memory at one record instead of the whole ledger.
    """
    p = ledger_path(root)
    if not p.exists():
        return {}
    summary: dict[str, tuple[str, str]] = {}
    try:
        with p.open(encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    rec = json.loads(s)
                except json.JSONDecodeError:
                    continue  # `validate` reports these; the index just skips them
                if not isinstance(rec, dict):
                    continue
                rid = rec.get("id")
                if rid:
                    summary[rid] = (rec.get("auditor", "?"), rec.get("status", "fixed"))
    except OSError as e:
        _note(None, f"{p}: cannot read: {e}")
    return summary


def _ledger_line(record: dict) -> str:
    # sort_keys keeps a record's serialization stable so git diffs stay minimal.
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def append_ledger(root: Path, record: dict) -> None:
    """Append one record, as a single write(2) plus fsync.

    Buffered text I/O would split a record larger than io.DEFAULT_BUFFER_SIZE
    into several syscalls, letting a concurrent appender interleave mid-record —
    read_ledger then drops both mangled lines silently. One os.write keeps the
    append atomic up to the OS limit; `store_lock` is the real guarantee above
    that. The fsync makes the append the durable commit point, so `resolve` can
    delete the open file knowing the ledger record survived.

    That commit point only holds if the append lands whole and at a line start,
    so both are checked: appending onto a newline-less last line would merge two
    records into one unparseable line, and a short write would commit half a
    record. Either way `resolve` would then delete an open file whose ledger
    record does not exist. Raise instead — like write_ledger, the damaged bytes
    are the only surviving evidence.
    """
    p = ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = (_ledger_line(record) + "\n").encode("utf-8")
    fd = os.open(p, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        if os.lseek(fd, 0, os.SEEK_END) > 0:
            os.lseek(fd, -1, os.SEEK_END)
            if os.read(fd, 1) != b"\n":
                raise FindingError(
                    f"{p}: last line is truncated (no trailing newline) — "
                    "repair the ledger before resolving"
                )
        written = os.write(fd, data)
        if written != len(data):
            raise FindingError(
                f"{p}: short write ({written}/{len(data)} bytes) — "
                "ledger truncated, repair before retrying"
            )
        os.fsync(fd)
    finally:
        os.close(fd)


def write_ledger(root: Path, records: list[dict]) -> None:
    """Rewrite the whole ledger, refusing to run if that would lose data.

    read_ledger skips lines it cannot parse, so rewriting from its output would
    silently erase them — and a corrupt line is exactly the state where the raw
    bytes are the only surviving evidence. Fail loudly instead; the operator
    repairs or removes the line deliberately.
    """
    p = ledger_path(root)
    errors: list[str] = []
    read_ledger(root, errors)
    if errors:
        raise FindingError(
            f"refusing to rewrite {p}: {len(errors)} unparseable line(s) would be lost:\n"
            + "\n".join(errors)
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    # PID-suffixed: a fixed tmp name is shared mutable state, so two concurrent
    # writers interleave into it and both then rename it over the real ledger.
    tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
    # fsync before the rename: resolve deletes the open finding file after this
    # returns, so the rename reaching disk ahead of the data would lose the whole
    # ledger on a crash. append_ledger already provides this durability.
    with tmp.open("w", encoding="utf-8") as f:
        f.write("".join(_ledger_line(r) + "\n" for r in records))
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(p)


def _record_from_finding(
    fm: dict[str, str], title: str, body: str, status: str, resolved: str, fid: str
) -> dict:
    extra = {k: v for k, v in fm.items() if k not in _KNOWN_FM}
    rec: dict[str, object] = {
        "id": fm.get("id", fid),
        "auditor": fm.get("auditor", ""),
        "severity": fm.get("severity", ""),
        "category": fm.get("category", ""),
        "area": fm.get("area", ""),
        "status": status,
        "found": fm.get("found", ""),
        "resolved": resolved,
        "title": title,
        "body": body,
    }
    if extra:
        rec["extra"] = extra
    return rec


def _note(errors: list[str] | None, msg: str) -> None:
    if errors is None:
        print(f"  WARNING  {msg}", file=sys.stderr)
    else:
        errors.append(msg)


# ── release-gate baseline (docs/audit/findings/baseline.json) ─────────────────
#
# A baseline is the set of finding IDs accepted at adoption time. `release-gate`
# fails only on open findings whose id is NOT in the baseline, so pre-existing
# debt is waived (but stays a real open finding) while any NEW finding blocks.
# IDs are content-hashed, so a genuinely new finding gets a new id and is caught.


def baseline_path(root: Path) -> Path:
    return root / BASELINE_NAME


def read_baseline(root: Path, errors: list[str] | None = None) -> set[str]:
    """The set of accepted finding IDs (empty if there is no baseline).

    A damaged baseline degrades to "no waivers", which is indistinguishable from
    an empty one unless it is reported: the operator sees every waived finding
    resurface as new, re-runs `baseline` to re-accept them, and overwrites the
    damaged file — erasing the record of what was originally waived. Report it.
    """
    p = baseline_path(root)
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _note(errors, f"{p}: unreadable baseline, treating as empty: {e}")
        return set()
    ids = data.get("ids") if isinstance(data, dict) else None
    if not isinstance(ids, list):
        _note(errors, f"{p}: baseline has no 'ids' list, treating as empty")
        return set()
    return {str(i) for i in ids}


def write_baseline(root: Path, ids: list[str], created: str) -> Path:
    p = baseline_path(root)
    payload = {"created": created, "ids": sorted(set(ids))}
    # Locked and PID-suffixed for the reason write_ledger states: a fixed tmp
    # name is shared mutable state, so two concurrent writers interleave into it
    # and both then rename the spliced file over the real baseline.
    with store_lock(root):
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(p)
    return p


def clear_baseline(root: Path) -> bool:
    p = baseline_path(root)
    if p.exists():
        p.unlink()
        return True
    return False


# ── review-hygiene: keep the store out of PR review noise ─────────────────────


def find_repo_root(start: Path) -> Path | None:
    p = start.resolve()
    for cand in (p, *p.parents):
        if (cand / ".git").exists():
            return cand
    return None


def _pattern_covers(pattern: str, rel: str) -> bool:
    """Crude prefix cover: does a gitignore/gitattributes `pattern` match `rel`
    (POSIX path) as itself or an ancestor directory? Enough for the store's one
    fixed path; not a full gitignore engine. A pattern naming a *descendant* of
    `rel` (e.g. one file inside the store) does not cover the store."""
    base = pattern.replace("**", "").rstrip("*").rstrip("/")
    if not base:
        return False
    return rel == base or rel.startswith(base + "/")


def _store_rel(root: Path) -> str:
    repo = find_repo_root(root)
    if repo is None:
        return "docs/audit/findings"
    try:
        return root.resolve().relative_to(repo).as_posix()
    except ValueError:
        return "docs/audit/findings"


def is_store_gitignored(root: Path) -> bool:
    repo = find_repo_root(root)
    if repo is None:
        return False
    rel = _store_rel(root)
    gi = repo / ".gitignore"
    if not gi.exists():
        return False
    try:
        lines = gi.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("!"):
            continue
        if _pattern_covers(s.rstrip("/").lstrip("/"), rel):
            return True
    return False


def store_gitattributes_present(root: Path) -> bool:
    ga = root / _STORE_GITATTRIBUTES
    try:
        return ga.exists() and _GITATTR_MARK in ga.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def ensure_store_gitattributes(root: Path) -> None:
    """Write the in-store .gitattributes marking findings generated, unless the
    store is gitignored or the mark is already present. The skill manages this
    file in its own domain; it never touches the repo-root .gitattributes."""
    if not root.exists() or is_store_gitignored(root) or store_gitattributes_present(root):
        return
    try:
        root.mkdir(parents=True, exist_ok=True)
        (root / _STORE_GITATTRIBUTES).write_text(_STORE_GITATTRIBUTES_BODY, encoding="utf-8")
    except OSError:
        pass


def check_review_hygiene(root: Path) -> str | None:
    """Warn if the store is neither marked generated (its own .gitattributes)
    nor gitignored — either way audit runs would flood PR diffs."""
    if is_store_gitignored(root) or store_gitattributes_present(root):
        return None
    return (
        "PR-review hygiene: the findings store is neither marked "
        "'linguist-generated' (in its own .gitattributes) nor gitignored, so "
        "audit runs will flood PR diffs. Add "
        f"'{(root / _STORE_GITATTRIBUTES).as_posix()}' with '** linguist-generated=true' "
        "(findings.py writes it automatically on index) or gitignore the store."
    )


# ── open findings (docs/audit/findings/<auditor>/open/<id>.md) ────────────────


def iter_open(
    root: Path, errors: list[str] | None = None
) -> list[tuple[Path, dict[str, str], str]]:
    """Parse every open finding file; unreadable files go to `errors` (or
    stderr) instead of crashing."""
    out = []
    for path in sorted(root.glob("*/open/*.md")):
        try:
            fm, title, _ = parse_finding(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            _note(errors, f"{path}: cannot read: {e}")
            continue
        out.append((path, fm, title))
    return out


def new_finding(
    root: Path,
    auditor: str,
    severity: str,
    category: str,
    area: str,
    title: str,
    body: str = "",
    found: str | None = None,
    force: bool = False,
) -> Path:
    _check_auditor(auditor)
    # Redact before hashing: the id is derived from title+area, so redacting
    # first keeps the id stable for the text actually written to disk.
    title = redact(title)
    area = redact(area)
    fid = finding_id(auditor, area, title)
    if not body.strip():
        body = "\n\n".join(f"## {s}\n" for s in OPEN_SECTIONS)
    body = redact(body)
    fm = {
        "id": fid,
        "auditor": auditor,
        "severity": severity,
        "category": category,
        "area": area,
        "status": "open",
        "found": found or _today(),
    }
    path = root / auditor / "open" / f"{fid}.md"
    with store_lock(root):
        # One parse, reused: read_ledger is the expensive call, and re-reading it
        # for the rewrite below both wastes the work and widens the race window.
        records = read_ledger(root)
        ledger = {r["id"]: r for r in records if r.get("id")}
        if not force:
            if path.exists():
                try:
                    efm, etitle, _ = parse_finding(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    efm, etitle = {}, ""
                if (etitle, efm.get("area", "")) != (title, area):
                    raise FindingError(
                        f"id collision with different finding ({etitle!r}) at {path}"
                    )
                raise FindingError(
                    f"finding {fid} already exists at {path}; use --force to overwrite"
                )
            if fid in ledger:
                raise FindingError(
                    f"finding {fid} already exists (resolved) in the ledger; use --force to re-open"
                )
        elif fid in ledger:
            # Re-opening a resolved finding: drop its ledger record so it is not both.
            write_ledger(root, [r for r in records if r.get("id") != fid])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(render_finding(fm, title, body), encoding="utf-8")
        tmp.replace(path)
    return path


def resolve_finding(
    root: Path,
    fid: str,
    status: str,
    notes: str,
    date: str | None = None,
    force: bool = False,
) -> Path:
    if status not in ("fixed", "invalid"):
        raise FindingError(f"resolve status must be fixed|invalid, got {status!r}")
    # Notes land in the append-only ledger, where a leaked secret is permanent.
    notes = redact(notes)
    _check_id(fid)
    if date is not None and not _DATE.match(date):
        raise FindingError(f"invalid --date {date!r}: want YYYY-MM-DD")
    resolved_at = date or _today()
    # The whole read-modify-write plus the unlink is one critical section: split
    # apart, two concurrent resolves compute their rewrite from the same snapshot,
    # the second drops the first's record, and both delete their open file — so
    # the losing finding survives in neither half of the store.
    with store_lock(root):
        records = read_ledger(root)  # one parse, reused for every rewrite below
        ledger = {r["id"]: r for r in records if r.get("id")}
        matches = sorted(root.glob(f"*/open/{fid}.md"))

        if fid in ledger and not force:
            raise FindingError(f"{fid} is already resolved; use --force to re-resolve")

        if not matches:
            if fid in ledger:  # force re-resolve of an already-resolved finding
                rec = dict(ledger[fid])
                rec["status"] = status
                rec["resolved"] = resolved_at
                if notes.strip():
                    rec["body"] = (
                        _drop_trailing_resolution(rec.get("body", "")).rstrip()
                        + f"\n\n## Resolution\n{notes.strip()}\n"
                    )
                write_ledger(root, [r for r in records if r.get("id") != fid] + [rec])
                return ledger_path(root)
            raise FindingError(f"no open finding with id {fid} under {root}")

        path = matches[0]
        fm, title, body = parse_finding(path.read_text(encoding="utf-8"))
        if "auditor" not in fm:
            fm["auditor"] = path.parent.parent.name
        _check_auditor(fm["auditor"])
        if notes.strip():
            body = (
                _drop_trailing_resolution(body).rstrip() + f"\n\n## Resolution\n{notes.strip()}\n"
            )
        rec = _record_from_finding(fm, title, body, status, resolved_at, fid)
        if fid in ledger:
            write_ledger(root, [r for r in records if r.get("id") != fid] + [rec])
        else:
            append_ledger(root, rec)  # fsynced: this is the commit point
        # missing_ok: a concurrent/repeated resolve may have already removed the
        # open file between the glob above and here — treat that as an idempotent
        # no-op rather than crashing with an uncaught FileNotFoundError.
        path.unlink(missing_ok=True)
    return ledger_path(root)


def show_finding(root: Path, fid: str) -> str:
    _check_id(fid)
    matches = sorted(root.glob(f"*/open/{fid}.md"))
    if matches:
        return matches[0].read_text(encoding="utf-8")
    rec = resolved_records(root).get(fid)
    if rec:
        fm = {k: rec.get(k, "") for k in _KNOWN_FM}
        if isinstance(rec.get("extra"), dict):
            fm.update(rec["extra"])
        return render_finding(fm, rec.get("title", ""), rec.get("body", ""))
    raise FindingError(f"no finding with id {fid} under {root}")


# ── validation ────────────────────────────────────────────────────────────────


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []

    def err(msg: str) -> None:
        errors.append(f"{path}: {msg}")

    try:
        fm, title, body = parse_finding(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as e:
        return [f"{path}: cannot read: {e}"]
    if not fm:
        return [f"{path}: missing frontmatter"]

    fid = fm.get("id", "")
    status = fm.get("status", "")
    if not fid:
        err("missing id")
    elif not (_LEGACY_ID.match(fid) or _HASH_ID.match(fid)):
        err(f"malformed id {fid!r}")
    if fid and path.stem != fid:
        err(f"id {fid!r} does not match filename {path.stem!r}")

    for key in ("auditor", "status", "found"):
        if not fm.get(key):
            err(f"missing {key}")
    if status and status not in STATUSES:
        err(f"invalid status {status!r}")
    if fm.get("found") and not _DATE.match(fm["found"]):
        err(f"invalid found date {fm['found']!r}")

    severity = fm.get("severity", "")
    category = fm.get("category", "")
    if severity and severity not in SEVERITIES:
        err(f"invalid severity {severity!r}")
    if category and category not in CATEGORIES:
        err(f"invalid category {category!r}")

    parent = path.parent.name
    if parent == "open" and status != "open":
        err(f"file in open/ but status is {status!r}")
    elif parent == "resolved" and status not in ("fixed", "invalid"):
        err(f"file in resolved/ but status is {status!r}")
    elif parent not in ("open", "resolved"):
        err(f"file not under open/ or resolved/ (found {parent!r})")

    auditor = fm.get("auditor", "")
    if auditor and path.parent.parent.name != auditor:
        err(f"auditor {auditor!r} does not match directory {path.parent.parent.name!r}")

    if status == "open":
        if not severity:
            err("missing severity")
        if not category:
            err("missing category")
        if not fm.get("area"):
            err("missing area")
        visible = _strip_fenced(body)
        for section in OPEN_SECTIONS:
            if not re.search(rf"^## {section}\s*$", visible, re.MULTILINE):
                err(f"missing '## {section}' section")
    else:
        resolved = fm.get("resolved", "")
        if not resolved:
            err("resolved finding missing resolved date")
        elif not _DATE.match(resolved):
            err(f"invalid resolved date {resolved!r}")

    if not title:
        err("missing '# <title>' heading")
    return errors


def validate_ledger_record(rec: dict, path: Path, lineno: int) -> list[str]:
    errors: list[str] = []

    def err(msg: str) -> None:
        errors.append(f"{path}:{lineno}: {msg}")

    rid = rec.get("id", "")
    if not rid:
        err("missing id")
    elif not (_LEGACY_ID.match(rid) or _HASH_ID.match(rid)):
        err(f"malformed id {rid!r}")
    if rec.get("status") not in ("fixed", "invalid"):
        err(f"resolved status must be fixed|invalid, got {rec.get('status')!r}")
    for key in ("auditor", "found", "resolved", "title"):
        if not rec.get(key):
            err(f"missing {key}")
    if rec.get("found") and not _DATE.match(str(rec["found"])):
        err(f"invalid found date {rec['found']!r}")
    if rec.get("resolved") and not _DATE.match(str(rec["resolved"])):
        err(f"invalid resolved date {rec['resolved']!r}")
    severity = rec.get("severity", "")
    category = rec.get("category", "")
    if severity and severity not in SEVERITIES:
        err(f"invalid severity {severity!r}")
    if category and category not in CATEGORIES:
        err(f"invalid category {category!r}")
    auditor = rec.get("auditor", "")
    if auditor and not _AUDITOR.match(auditor):
        err(f"invalid auditor {auditor!r}")
    return errors


def validate_store(root: Path) -> list[str]:
    errors: list[str] = []
    seen: dict[str, Path] = {}
    # A leftover legacy tree is the state an aborted `migrate-resolved` leaves
    # behind; without this sweep the store validates clean while findings sit in
    # a directory no command reads from.
    for path in sorted(root.glob("*/resolved/*.md")):
        errors.append(
            f"{path}: legacy resolved file outside the ledger — run 'findings.py migrate-resolved'"
        )
    for path, fm, _title in iter_open(root, errors):
        errors.extend(validate_file(path))
        fid = fm.get("id", path.stem)
        if fid in seen:
            errors.append(f"{path}: duplicate id {fid} (also in {seen[fid]})")
        else:
            seen[fid] = path

    lpath = ledger_path(root)
    if lpath.exists():
        try:
            raw = lpath.read_text(encoding="utf-8")
        except OSError as e:
            return [*errors, f"{lpath}: cannot read: {e}"]
        for i, line in enumerate(raw.splitlines(), 1):
            s = line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s)
            except json.JSONDecodeError as e:
                errors.append(f"{lpath}:{i}: invalid JSON: {e}")
                continue
            if not isinstance(rec, dict):
                errors.append(f"{lpath}:{i}: ledger line is not a JSON object")
                continue
            errors.extend(validate_ledger_record(rec, lpath, i))
            rid = rec.get("id", "")
            if rid and rid in seen:
                # A finding cannot be both open (a file) and resolved (the ledger).
                errors.append(f"{lpath}:{i}: id {rid} is also open at {seen[rid]}")
    return errors


# ── index ─────────────────────────────────────────────────────────────────────


def build_index(root: Path) -> str:
    rows: dict[str, dict[str, int]] = {}
    open_findings: list[tuple[int, str, dict[str, str], str, Path]] = []
    for path, fm, title in iter_open(root):
        auditor = fm.get("auditor", path.parent.parent.name)
        counts = rows.setdefault(auditor, {"open": 0, "fixed": 0, "invalid": 0})
        counts["open"] += 1
        rank = SEVERITIES.index(fm["severity"]) if fm.get("severity") in SEVERITIES else 99
        open_findings.append((rank, fm.get("id", path.stem), fm, title, path))

    # Streamed, not materialised: only `auditor` and `status` are used here, but
    # every record carries the finding's whole body. resolved_records() would
    # decode all of them into memory (~50 MB at 10k records) to count two ints.
    # Still keyed by id so a re-resolved finding counts once, last line winning.
    for rid, (auditor, status) in _ledger_summary(root).items():
        counts = rows.setdefault(auditor, {"open": 0, "fixed": 0, "invalid": 0})
        if status in ("fixed", "invalid"):
            counts[status] += 1
        else:
            # Out-of-vocab ledger status has no column; surface it instead of
            # silently dropping it while `validate` still flags it.
            print(
                f"  WARNING  ledger: out-of-vocab status {status!r} for {rid}",
                file=sys.stderr,
            )

    totals = {"open": 0, "fixed": 0, "invalid": 0}
    table_rows: list[list[str]] = []
    for auditor in sorted(rows):
        c = rows[auditor]
        table_rows.append([auditor, str(c["open"]), str(c["fixed"]), str(c["invalid"])])
        for key in totals:
            totals[key] += c[key]
    table_rows.append(
        ["**total**", str(totals["open"]), str(totals["fixed"]), str(totals["invalid"])]
    )
    lines = [
        "# Audit Findings Index",
        "",
        "Generated by `findings.py index` — do not edit by hand.",
        "",
        "## Summary",
        "",
        *_render_table(["Auditor", "Open", "Fixed", "Invalid"], table_rows),
        "",
        "## Open findings",
        "",
    ]
    if open_findings:
        for _rank, fid, fm, title, path in sorted(open_findings, key=lambda x: (x[0], x[1])):
            rel = path.as_posix()
            lines.append(
                f"- **{fm.get('severity', '?')}** [{fid}] {title} — `{fm.get('area', '?')}` ({rel})"
            )
    else:
        lines.append("(none)")
    return "\n".join(lines) + "\n"


def write_index(root: Path) -> Path:
    # Managing the store's own review-hygiene mark rides along with the index
    # refresh that every mutating command already runs.
    ensure_store_gitattributes(root)
    path = root / "INDEX.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    # tmp+replace like every other writer here: INDEX.md has three concurrent
    # writers (CLI, MCP server, PostToolUse hook), and a bare write_text truncates
    # then streams, so two builds interleave into one spliced file.
    with store_lock(root):
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(build_index(root), encoding="utf-8")
        tmp.replace(path)
    return path


# ── migration ─────────────────────────────────────────────────────────────────


def migrate_resolved(root: Path, dry_run: bool = False) -> tuple[int, int]:
    """Convert legacy <auditor>/resolved/*.md files into resolved.jsonl and
    delete the ones that were recorded. Idempotent: a byte-identical record
    already in the ledger is skipped, and its file is still removed.

    Legacy v1 ids are hand-assigned (`_LEGACY_ID`), so the same id genuinely
    recurs across auditor directories. A file whose id is already in the ledger
    with DIFFERENT content is a conflict, not a duplicate: it aborts the run
    rather than being deleted unrecorded.
    """
    files = sorted(root.glob("*/resolved/*.md"))
    with store_lock(root):
        existing = resolved_records(root)
        planned: list[tuple[Path, dict]] = []
        conflicts: list[str] = []
        deletable: list[Path] = []

        for path in files:
            try:
                fm, title, body = parse_finding(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as e:
                raise FindingError(f"{path}: cannot read: {e}") from e
            fid = fm.get("id", path.stem)
            status = fm.get("status", "fixed")
            if status not in ("fixed", "invalid"):
                raise FindingError(f"{path}: unrecognised status {status!r}; want fixed|invalid")
            if "auditor" not in fm:
                fm["auditor"] = path.parent.parent.name
            resolved = fm.get("resolved", "") or fm.get("found", "")
            rec = _record_from_finding(fm, title, body, status, resolved or "1970-01-01", fid)
            if not resolved:
                # Mark the synthesised date so a reader can tell it from a real
                # one, and so later date arithmetic cannot silently trust it.
                rec["date_synthesised"] = True
            if fid not in existing:
                planned.append((path, rec))
            elif _comparable(existing[fid]) != _comparable(rec):
                conflicts.append(f"{path}: id {fid} already in the ledger with different content")
            else:
                deletable.append(path)

        if conflicts:
            raise FindingError(
                "refusing to delete unrecorded findings — resolve these manually:\n"
                + "\n".join(conflicts)
            )
        if dry_run:
            for path, rec in planned:
                print(f"WOULD APPEND {rec['id']} from {path}")
            for path in [*(p for p, _ in planned), *deletable]:
                print(f"WOULD DELETE {path}")
            return len(planned), len(planned) + len(deletable)

        for _path, rec in planned:
            append_ledger(root, rec)
            existing[rec["id"]] = rec
        # Only now, with every record durably appended, remove the sources.
        for path in [*(p for p, _ in planned), *deletable]:
            path.unlink()
        for d in sorted(root.glob("*/resolved")):
            with contextlib.suppress(OSError):  # only removes an already-empty dir
                d.rmdir()
    return len(planned), len(planned) + len(deletable)


def _comparable(rec: dict) -> tuple:
    """The fields that decide whether two ledger records are the same finding."""
    return (rec.get("title", ""), rec.get("body", ""), rec.get("status", ""))


def _build_v1(
    root: Path,
    auditor: str,
    entry: dict[str, str],
    fields: dict[str, str],
    generated: str,
    src_name: str,
) -> tuple | None:
    """Render one parsed v1 finding as a plan item: ('open', id, path, content)
    or ('resolved', id, record). Writing is deferred to migrate_v1 so a mid-run
    duplicate cannot leave a half-written store."""
    if not entry:
        return None
    _check_auditor(auditor)
    status = entry["status"]
    fid = entry["id"]
    if status == "open":
        fm = {
            "id": fid,
            "auditor": auditor,
            "severity": entry.get("severity", ""),
            "category": fields.get("Category", ""),
            "area": fields.get("Area", ""),
            "status": "open",
            "found": generated or "1970-01-01",
        }
        body = "\n\n".join(f"## {s}\n{fields.get(s, '').strip()}" for s in OPEN_SECTIONS)
        path = root / auditor / "open" / f"{fid}.md"
        return ("open", fid, path, render_finding(fm, entry["title"], body))

    resolved = fields.get("Fixed", "") or entry.get("pass_date", "") or generated or "1970-01-01"
    notes = fields.get("Notes", "").strip()
    body = f"## Resolution\n{notes}" if notes else "## Resolution\n(none recorded)"
    pass_bits = ", ".join(
        bit
        for bit in (
            f"Pass {entry['pass_n']}" if entry.get("pass_n") else "",
            entry.get("pass_date", ""),
        )
        if bit
    )
    provenance = f"Migrated from v1 `{src_name}`" + (f" ({pass_bits})" if pass_bits else "")
    body += f"\n\n{provenance}."
    rec = {
        "id": fid,
        "auditor": auditor,
        "severity": "",
        "category": "",
        "area": "",
        "status": status,
        "found": generated or "1970-01-01",
        "resolved": resolved,
        "title": entry["title"],
        "body": body,
    }
    return ("resolved", fid, rec)


def migrate_v1(src: Path, root: Path, dry_run: bool = False) -> int:
    text = src.read_text(encoding="utf-8")
    auditor = v1_auditor(src.name)
    generated = ""
    section = ""  # open | fixed | invalid
    severity = ""
    pass_date = ""
    pass_n = ""
    entry: dict[str, str] = {}
    fields: dict[str, str] = {}
    last_field = ""
    in_fence = False
    buffered: list[tuple] = []
    known_sections = {
        "open findings": "open",
        "fixed": "fixed",
        "invalid": "invalid",
        "summary": "",
    }

    def flush() -> None:
        nonlocal entry, fields, last_field
        built = _build_v1(root, auditor, entry, fields, generated, src.name)
        if built:
            buffered.append(built)
        entry, fields, last_field = {}, {}, ""

    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            # A fence inside a field value is content, not structure.
            if entry and last_field:
                fields[last_field] += "\n" + line
            continue
        if in_fence:
            if entry and last_field:
                fields[last_field] += "\n" + line
            continue
        m = _V1_GENERATED.match(line)
        if m and not generated:
            generated = m.group(1)
            continue
        if line.startswith("## "):
            name = line[3:].strip().lower()
            if name in known_sections:
                flush()
                section = known_sections[name]
                continue
            if not entry:
                raise FindingError(f"unrecognized v1 section {name!r} in {src.name}")
            # else: an unrecognized '## ' heading inside a finding is field
            # content — fall through to the field-continuation handling below.
        elif line.startswith("### ") and not line.startswith("####") and not entry:
            if section == "open":
                severity = line[4:].strip().lower()
            else:
                m = _V1_PASS.match(line)
                pass_n = m.group(1) if m else ""
                pass_date = m.group(2) if m else ""
            continue
        m = _V1_FINDING.match(line)
        if m and section:
            flush()
            entry = {
                "id": m.group(1),
                "title": m.group(2).strip(),
                "status": section if section != "open" else "open",
                "severity": severity if section == "open" else "",
                "pass_date": pass_date,
                "pass_n": pass_n,
            }
            continue
        if entry:
            m = _V1_FIELD.match(line)
            allowed = (
                ("Category", "Area", "Problem", "Evidence", "Impact", "Fix")
                if entry["status"] == "open"
                else ("Fixed", "Notes")
            )
            if m and m.group(1) in allowed and m.group(1) not in fields:
                last_field = m.group(1)
                fields[last_field] = m.group(2)
            elif last_field:
                # Blank lines and prose (even "Field:"-shaped) continue the open field.
                fields[last_field] += "\n" + line
    flush()

    # Dry-run first: an in-run duplicate id must abort BEFORE any write, so a bad
    # source can never leave a half-migrated store behind.
    planned: dict[str, tuple] = {}
    for item in buffered:
        fid = item[1]
        if fid in planned:
            raise FindingError(f"duplicate id {fid} while migrating {src.name}")
        planned[fid] = item

    # Locked like migrate_resolved: the duplicate-id guards below read the ledger
    # and the open tree, then write. Without the lock a concurrent `resolve` can
    # land between the check and the write, leaving a finding both in the ledger
    # and open — a state `validate` rejects and no single command created.
    with store_lock(root):
        existing_resolved = resolved_records(root)
        to_write_files: list[tuple[Path, str]] = []
        to_append: list[dict] = []
        for fid, item in planned.items():
            if item[0] == "open":
                path, content = item[2], item[3]
                if fid in existing_resolved:
                    raise FindingError(f"duplicate id {fid} while migrating {src.name}")
                if path.exists():
                    if path.read_text(encoding="utf-8") == content:
                        continue  # already migrated identically — re-running is a no-op
                    raise FindingError(f"duplicate id {fid} while migrating {src.name}")
                to_write_files.append((path, content))
            else:  # resolved
                if fid in existing_resolved:
                    continue  # already in the ledger — idempotent re-run
                if list(root.glob(f"*/open/{fid}.md")):
                    raise FindingError(f"duplicate id {fid} while migrating {src.name}")
                to_append.append(item[2])

        if dry_run:
            for path, _content in to_write_files:
                print(f"WOULD WRITE {path}")
            for rec in to_append:
                print(f"WOULD APPEND {rec['id']}")
            return len(to_write_files) + len(to_append)

        for path, content in to_write_files:
            path.parent.mkdir(parents=True, exist_ok=True)
            # tmp+replace like every other writer here: a bare write_text truncates,
            # and an interrupted migration would leave a partial file that the
            # idempotence check above then reports as a misleading "duplicate id".
            tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
        for rec in to_append:
            append_ledger(root, rec)
        return len(to_write_files) + len(to_append)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add_root(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", type=Path, default=DEFAULT_ROOT)

    p_new = sub.add_parser("new", help="create an open finding")
    add_root(p_new)
    p_new.add_argument("--auditor", required=True)
    p_new.add_argument("--severity", required=True, choices=SEVERITIES)
    p_new.add_argument("--category", required=True, choices=CATEGORIES)
    p_new.add_argument("--area", required=True)
    p_new.add_argument("--body", default="", help="markdown body; '-' reads stdin")
    p_new.add_argument("--force", action="store_true", help="overwrite an existing finding")
    p_new.add_argument("title")

    p_res = sub.add_parser("resolve", help="mark a finding fixed/invalid")
    add_root(p_res)
    p_res.add_argument("id")
    p_res.add_argument("--status", required=True, choices=("fixed", "invalid"))
    p_res.add_argument("--notes", required=True)
    p_res.add_argument("--date", default=None)
    p_res.add_argument(
        "--force", action="store_true", help="re-resolve an already-resolved finding"
    )

    p_list = sub.add_parser("list", help="list findings")
    add_root(p_list)
    p_list.add_argument("--auditor", default=None)
    p_list.add_argument("--status", default=None, choices=STATUSES)
    p_list.add_argument(
        "--exclude-baseline",
        action="store_true",
        help="omit findings whose id is in the release-gate baseline",
    )

    p_show = sub.add_parser("show", help="print one finding (open file or resolved ledger)")
    add_root(p_show)
    p_show.add_argument("id")

    p_val = sub.add_parser("validate", help="validate the store or given files")
    add_root(p_val)
    p_val.add_argument("paths", nargs="*", type=Path)

    p_idx = sub.add_parser("index", help="regenerate INDEX.md")
    add_root(p_idx)

    p_base = sub.add_parser(
        "baseline", help="snapshot open findings as an accepted release-gate baseline"
    )
    add_root(p_base)
    p_base.add_argument("--clear", action="store_true", help="remove the baseline")
    p_base.add_argument(
        "--force", action="store_true", help="overwrite an existing baseline (review the diff)"
    )

    # --dry-run on both: these are the only bulk store rewrites, and one of them
    # deletes its sources, so the first run must not also be the only run.
    p_mig = sub.add_parser("migrate", help="convert v1 *-findings.md files")
    add_root(p_mig)
    p_mig.add_argument("sources", nargs="+", type=Path)
    p_mig.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")

    p_mr = sub.add_parser(
        "migrate-resolved", help="convert legacy resolved/*.md files into resolved.jsonl"
    )
    add_root(p_mr)
    p_mr.add_argument("--dry-run", action="store_true", help="print the plan, change nothing")

    args = parser.parse_args(argv)

    if args.cmd == "new":
        body = sys.stdin.read() if args.body == "-" else args.body
        try:
            path = new_finding(
                args.root,
                args.auditor,
                args.severity,
                args.category,
                args.area,
                args.title,
                body,
                force=args.force,
            )
        except FindingError as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 1
        # INDEX.md is generated from the store, and `make check`/CI fail when the
        # two drift. mcp_server.py regenerates after every mutation; the CLI must
        # too, or the documented way to close a finding leaves a red build.
        write_index(args.root)
        print(path)
        return 0

    if args.cmd == "resolve":
        try:
            path = resolve_finding(
                args.root, args.id, args.status, args.notes, args.date, force=args.force
            )
        except FindingError as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 1
        write_index(args.root)
        print(path)
        return 0

    if args.cmd == "list":
        entries: list[tuple[str, str, str, str, str]] = []
        for path, fm, title in iter_open(args.root):
            entries.append(
                (
                    fm.get("id", path.stem),
                    fm.get("status", "open"),
                    fm.get("severity", "-"),
                    title,
                    fm.get("auditor", "?"),
                )
            )
        for rec in sorted(resolved_records(args.root).values(), key=lambda r: r.get("id", "")):
            entries.append(
                (
                    rec.get("id", "?"),
                    rec.get("status", "?"),
                    rec.get("severity") or "-",
                    rec.get("title", ""),
                    rec.get("auditor", "?"),
                )
            )
        baselined = read_baseline(args.root) if args.exclude_baseline else set()
        for fid, status, severity, title, auditor in entries:
            if args.auditor and auditor != args.auditor:
                continue
            if args.status and status != args.status:
                continue
            if fid in baselined:
                continue
            print(f"{fid:24} {status:8} {severity:9} {title}")
        return 0

    if args.cmd == "show":
        try:
            print(show_finding(args.root, args.id), end="")
        except FindingError as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 1
        return 0

    if args.cmd == "validate":
        if args.paths:
            errors = [e for p in args.paths for e in validate_file(p)]
        elif args.root.exists():
            errors = validate_store(args.root)
        else:
            print(f"OK  {args.root} not found; nothing to check.")
            return 0
        if not args.paths:
            warn = check_review_hygiene(args.root)
            if warn:
                print(f"  WARNING  {warn}")
        for e in errors:
            print(f"  ERROR  {e}")
        if errors:
            print(f"\n{len(errors)} error(s) in findings store.")
            return 1
        print("OK  findings store consistent.")
        return 0

    if args.cmd == "index":
        print(write_index(args.root))
        return 0

    if args.cmd == "baseline":
        if args.clear:
            print("baseline cleared" if clear_baseline(args.root) else "no baseline to clear")
            return 0
        if baseline_path(args.root).exists() and not args.force:
            print(
                f"ERROR  {baseline_path(args.root)} already exists; re-baselining can absorb "
                "findings filed since. Use --clear first, or --force after reviewing the diff.",
                file=sys.stderr,
            )
            return 1
        open_ids = sorted(fm.get("id", path.stem) for path, fm, _ in iter_open(args.root))
        out = write_baseline(args.root, open_ids, _today())
        print(f"{out}: baselined {len(open_ids)} open finding(s)")
        return 0

    if args.cmd == "migrate":
        total = 0
        for src in args.sources:
            try:
                n = migrate_v1(src, args.root, dry_run=args.dry_run)
            except (FindingError, OSError, UnicodeDecodeError) as e:
                print(f"ERROR  {src}: {e}", file=sys.stderr)
                return 1
            print(f"{src}: {'would migrate' if args.dry_run else 'migrated'} {n} finding(s)")
            total += n
        if args.dry_run:
            print(f"dry run: would migrate {total} finding(s) in total")
            return 0
        write_index(args.root)
        print(f"total: {total}")
        return 0

    if args.cmd == "migrate-resolved":
        try:
            appended, total = migrate_resolved(args.root, dry_run=args.dry_run)
        except (FindingError, OSError, UnicodeDecodeError) as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 1
        if args.dry_run:
            print(f"dry run: would migrate {appended} finding(s), remove {total} file(s)")
            return 0
        write_index(args.root)
        print(
            f"migrated {appended} resolved finding(s) into {ledger_path(args.root)} "
            f"({total} file(s) removed)"
        )
        return 0

    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
