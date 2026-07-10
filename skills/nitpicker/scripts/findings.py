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
    migrate-resolved convert legacy <auditor>/resolved/*.md files into the ledger
"""

import argparse
import contextlib
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path("docs/audit/findings")
LEDGER_NAME = "resolved.jsonl"
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

    Inlined from scripts/common.py so the shipped skill tool has no imports
    outside the standard library.
    """
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ": " in line:
            k, _, v = line.partition(": ")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
                v = v[1:-1]
            fm[k.strip()] = v
    return fm, text[end + 5 :]


def _today() -> str:
    return datetime.date.today().isoformat()


def _check_auditor(auditor: str) -> None:
    """Reject auditor keys that are not plain kebab-case (they become path parts)."""
    if not _AUDITOR.match(auditor):
        raise FindingError(f"invalid auditor {auditor!r}: want lowercase kebab-case")


def _check_id(fid: str) -> None:
    if not (_LEGACY_ID.match(fid) or _HASH_ID.match(fid)):
        raise FindingError(f"malformed finding id {fid!r}")


def finding_id(auditor: str, area: str, title: str) -> str:
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
    known = ("id", "auditor", "severity", "category", "area", "status", "found", "resolved")
    if "\n" in title:
        raise FindingError("title must be single-line")
    lines = ["---"]
    # Known keys in canonical order, then any extra keys (e.g. cve:) preserved.
    for key in (*known, *(k for k in fm if k not in known)):
        value = fm.get(key, "")
        if "\n" in value:
            # A newline would inject extra frontmatter lines (last-write-wins on parse).
            raise FindingError(f"frontmatter field {key!r} must be single-line")
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


def _ledger_line(record: dict) -> str:
    # sort_keys keeps a record's serialization stable so git diffs stay minimal.
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def append_ledger(root: Path, record: dict) -> None:
    p = ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(_ledger_line(record) + "\n")


def write_ledger(root: Path, records: list[dict]) -> None:
    p = ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text("".join(_ledger_line(r) + "\n" for r in records), encoding="utf-8")
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
    fid = finding_id(auditor, area, title)
    if not body.strip():
        body = "\n\n".join(f"## {s}\n" for s in OPEN_SECTIONS)
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
    ledger = resolved_records(root)
    if not force:
        if path.exists():
            try:
                efm, etitle, _ = parse_finding(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                efm, etitle = {}, ""
            if (etitle, efm.get("area", "")) != (title, area):
                raise FindingError(f"id collision with different finding ({etitle!r}) at {path}")
            raise FindingError(f"finding {fid} already exists at {path}; use --force to overwrite")
        if fid in ledger:
            raise FindingError(
                f"finding {fid} already exists (resolved) in the ledger; use --force to re-open"
            )
    elif fid in ledger:
        # Re-opening a resolved finding: drop its ledger record so it is not both.
        write_ledger(root, [r for r in read_ledger(root) if r.get("id") != fid])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
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
    _check_id(fid)
    if date is not None and not _DATE.match(date):
        raise FindingError(f"invalid --date {date!r}: want YYYY-MM-DD")
    ledger = resolved_records(root)
    matches = sorted(root.glob(f"*/open/{fid}.md"))
    resolved_at = date or _today()

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
            write_ledger(root, [r for r in read_ledger(root) if r.get("id") != fid] + [rec])
            return ledger_path(root)
        raise FindingError(f"no open finding with id {fid} under {root}")

    path = matches[0]
    fm, title, body = parse_finding(path.read_text(encoding="utf-8"))
    if "auditor" not in fm:
        fm["auditor"] = path.parent.parent.name
    _check_auditor(fm["auditor"])
    if notes.strip():
        body = _drop_trailing_resolution(body).rstrip() + f"\n\n## Resolution\n{notes.strip()}\n"
    rec = _record_from_finding(fm, title, body, status, resolved_at, fid)
    if fid in ledger:
        write_ledger(root, [r for r in read_ledger(root) if r.get("id") != fid] + [rec])
    else:
        append_ledger(root, rec)
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

    for rec in resolved_records(root).values():
        auditor = rec.get("auditor", "?")
        status = rec.get("status", "fixed")
        counts = rows.setdefault(auditor, {"open": 0, "fixed": 0, "invalid": 0})
        if status in ("fixed", "invalid"):
            counts[status] += 1
        else:
            # Out-of-vocab ledger status has no column; surface it instead of
            # silently dropping it while `validate` still flags it.
            print(
                f"  WARNING  ledger: out-of-vocab status {status!r} for {rec.get('id')}",
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
    path.write_text(build_index(root), encoding="utf-8")
    return path


# ── migration ─────────────────────────────────────────────────────────────────


def migrate_resolved(root: Path) -> tuple[int, int]:
    """Convert legacy <auditor>/resolved/*.md files into resolved.jsonl and
    delete them. Idempotent: a record already in the ledger is skipped."""
    files = sorted(root.glob("*/resolved/*.md"))
    existing = resolved_records(root)
    appended = 0
    for path in files:
        try:
            fm, title, body = parse_finding(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as e:
            raise FindingError(f"{path}: cannot read: {e}") from e
        fid = fm.get("id", path.stem)
        status = fm.get("status", "fixed")
        if status not in ("fixed", "invalid"):
            status = "fixed"
        if "auditor" not in fm:
            fm["auditor"] = path.parent.parent.name
        resolved = fm.get("resolved", "") or fm.get("found", "") or "1970-01-01"
        if fid not in existing:
            rec = _record_from_finding(fm, title, body, status, resolved, fid)
            append_ledger(root, rec)
            existing[fid] = rec
            appended += 1
    for path in files:
        path.unlink()
    for d in sorted(root.glob("*/resolved")):
        with contextlib.suppress(OSError):  # only removes an already-empty dir
            d.rmdir()
    return appended, len(files)


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


def migrate_v1(src: Path, root: Path) -> int:
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

    for path, content in to_write_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
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

    p_show = sub.add_parser("show", help="print one finding (open file or resolved ledger)")
    add_root(p_show)
    p_show.add_argument("id")

    p_val = sub.add_parser("validate", help="validate the store or given files")
    add_root(p_val)
    p_val.add_argument("paths", nargs="*", type=Path)

    p_idx = sub.add_parser("index", help="regenerate INDEX.md")
    add_root(p_idx)

    p_mig = sub.add_parser("migrate", help="convert v1 *-findings.md files")
    add_root(p_mig)
    p_mig.add_argument("sources", nargs="+", type=Path)

    p_mr = sub.add_parser(
        "migrate-resolved", help="convert legacy resolved/*.md files into resolved.jsonl"
    )
    add_root(p_mr)

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
        for fid, status, severity, title, auditor in entries:
            if args.auditor and auditor != args.auditor:
                continue
            if args.status and status != args.status:
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

    if args.cmd == "migrate":
        total = 0
        for src in args.sources:
            try:
                n = migrate_v1(src, args.root)
            except (FindingError, OSError, UnicodeDecodeError) as e:
                print(f"ERROR  {src}: {e}", file=sys.stderr)
                return 1
            print(f"{src}: migrated {n} finding(s)")
            total += n
        write_index(args.root)
        print(f"total: {total}")
        return 0

    if args.cmd == "migrate-resolved":
        try:
            appended, total = migrate_resolved(args.root)
        except (FindingError, OSError, UnicodeDecodeError) as e:
            print(f"ERROR  {e}", file=sys.stderr)
            return 1
        write_index(args.root)
        print(
            f"migrated {appended} resolved finding(s) into {ledger_path(args.root)} "
            f"({total} file(s) removed)"
        )
        return 0

    return 2  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
