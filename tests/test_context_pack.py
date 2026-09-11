"""Tests for skills/nitpicker/scripts/context_pack.py.

The property under test throughout is the one the module exists for: a pack
answers with coordinates and reasons, never with file bodies, and it says what
it left out. A test that only checked "returns something" would pass on a pack
that silently dropped the whole repository — the exact failure `omitted` exists
to make visible.
"""

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"))
import context_pack as cp


def _repo(tmp_path: Path, files: dict[str, str], commit: bool = True) -> Path:
    """A real git repository containing `files`, committed unless told otherwise.

    Real git rather than a stub: `_git`, `_tracked_files` and `_diff` all parse
    git's actual output, and a stub would pin this suite to the output shape
    assumed on the day it was written rather than the one git produces.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    if commit:
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


PY = '''\
"""Module docstring."""


def outer(x):
    """Doc."""
    return subprocess_call(x)


class Thing:
    def method(self):
        return 1
'''

JS = """\
export function alpha(a) {
  return a;
}

class Beta {
}
"""


# ── estimate / helpers ───────────────────────────────────────────────────────


def test_estimate_tokens_rounds_up_so_a_short_string_never_costs_zero():
    assert cp.estimate_tokens("") == 0
    assert cp.estimate_tokens("a") == 1
    assert cp.estimate_tokens("abcd") == 1
    assert cp.estimate_tokens("abcde") == 2


def test_language_falls_back_to_the_bare_suffix_rather_than_dropping_the_file():
    assert cp._language(Path("a.py")) == "python"
    assert cp._language(Path("a.PY")) == "python"
    assert cp._language(Path("a.zzz")) == "zzz"
    assert cp._language(Path("Makefile")) == "none"


def test_read_returns_none_for_a_binary_file_instead_of_raising(tmp_path):
    blob = tmp_path / "b.bin"
    blob.write_bytes(b"\xff\xfe\x00\x01")
    assert cp._read(blob, tmp_path) is None
    assert cp._read(tmp_path / "missing", tmp_path) is None


def test_git_raises_pack_error_naming_the_failure_rather_than_returning_empty(tmp_path):
    with pytest.raises(cp.PackError, match="failed"):
        cp._git(tmp_path, "rev-parse", "--verify", "definitely-not-a-ref")


def test_git_reports_a_missing_binary_as_a_pack_error(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("no git here")

    monkeypatch.setattr(cp.subprocess, "run", boom)
    with pytest.raises(cp.PackError, match="git is not available"):
        cp._git(tmp_path, "status")


def test_tracked_files_falls_back_to_a_walk_outside_a_repository(tmp_path):
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    skipped = tmp_path / "node_modules"
    skipped.mkdir()
    (skipped / "dep.js").write_text("//\n", encoding="utf-8")
    found = {p.name for p in cp._tracked_files(tmp_path)}
    assert "keep.py" in found
    assert "dep.js" not in found


def test_walk_skips_a_directory_it_cannot_read(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    real = Path.iterdir

    def flaky(self):
        if self.name == "locked":
            raise OSError("denied")
        return real(self)

    (tmp_path / "locked").mkdir()
    monkeypatch.setattr(Path, "iterdir", flaky)
    assert {p.name for p in cp._walk(tmp_path)} == {"a.py"}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX-only special file")
def test_walk_ignores_an_entry_that_is_neither_file_nor_directory(tmp_path):
    """A FIFO, not a dangling symlink: the symlink skip now runs first.

    Using a link here would exercise that skip instead and leave the
    neither-file-nor-directory fall-through untested — which is what happened,
    and coverage caught it.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    os.mkfifo(tmp_path / "pipe")
    assert {p.name for p in cp._walk(tmp_path)} == {"a.py"}


def test_walk_skips_a_dangling_symlink(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "dangling").symlink_to(tmp_path / "gone")
    assert {p.name for p in cp._walk(tmp_path)} == {"a.py"}


def test_walk_does_not_follow_a_self_referential_directory_symlink(tmp_path):
    """`is_dir()` follows a link, so `sub/link -> ..` re-enters its own ancestor.

    The walk would push that ancestor back on the stack forever. Nothing bounds
    it — no git runs on this path, so `GIT_TIMEOUT` does not apply — and
    `mcp_server` serves stdio single-threaded, so the hang would take every
    later tool call in the session with it.

    A timeout would make this test flaky and would still hang the suite on a
    regression; asserting the returned set is exact catches the same defect the
    moment the link is traversed even once.
    """
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.py").write_text("y = 2\n", encoding="utf-8")
    (sub / "loop").symlink_to(tmp_path, target_is_directory=True)
    assert {p.name for p in cp._walk(tmp_path)} == {"a.py", "b.py"}


def test_scoped_refuses_a_path_escaping_the_root(tmp_path):
    with pytest.raises(cp.PackError, match="escapes the project root"):
        cp._scoped(tmp_path, [], ["../elsewhere"])


def test_scoped_without_paths_is_a_passthrough(tmp_path):
    files = [tmp_path / "a.py"]
    assert cp._scoped(tmp_path, files, []) == files


# ── symbols ──────────────────────────────────────────────────────────────────


def test_python_symbols_come_from_ast_with_real_end_lines(tmp_path):
    outline = cp.symbols_of(Path("m.py"), PY)
    names = {n for n, _, _ in outline}
    assert names == {"outer", "Thing", "method"}
    start, end = next((s, e) for n, s, e in outline if n == "outer")
    assert start == 4 and end == 6


def test_python_syntax_error_falls_back_to_the_regex_outline():
    broken = "def alpha(:\n    pass\n\ndef beta():\n    pass\n"
    assert [n for n, _, _ in cp.symbols_of(Path("m.py"), broken)] == ["alpha", "beta"]


def test_non_python_uses_the_declaration_regex():
    assert [n for n, _, _ in cp.symbols_of(Path("m.js"), JS)] == ["alpha", "Beta"]


def test_regex_outline_ends_a_symbol_at_the_next_declaration():
    outline = cp.symbols_of(Path("m.js"), JS)
    alpha = next(item for item in outline if item[0] == "alpha")
    assert alpha[1] == 1 and alpha[2] == 4


def test_enclosing_prefers_the_innermost_declaration():
    outline = [("Thing", 9, 11), ("method", 10, 11)]
    assert cp._enclosing(outline, 10) == "method"
    assert cp._enclosing(outline, 9) == "Thing"
    assert cp._enclosing(outline, 99) == ""


def test_enclosing_is_innermost_regardless_of_outline_order():
    """Narrower wins even when the wider declaration is seen second.

    `symbols_of` happens to yield outer-before-inner, so ordering alone would
    give the right answer today and the wrong one the moment a provider yields
    a different order. The tie-break is on span, and this pins that.
    """
    assert cp._enclosing([("method", 10, 11), ("Thing", 9, 11)], 10) == "method"


# ── modes ────────────────────────────────────────────────────────────────────


def test_inventory_reports_every_file_and_no_source(tmp_path):
    root = _repo(tmp_path, {"a.py": PY, "b.js": JS})
    pack = cp.build(root=root, goal="", mode="inventory")
    rows = {row["path"]: row for row in pack["files"]}
    assert set(rows) == {"a.py", "b.js"}
    assert rows["a.py"]["language"] == "python"
    assert rows["a.py"]["lines"] > 1
    assert "source" not in rows["a.py"]
    assert json.dumps(pack).count("def outer") == 0


def test_inventory_notes_the_language_histogram(tmp_path):
    root = _repo(tmp_path, {"a.py": PY, "b.js": JS})
    pack = cp.build(root=root, goal="", mode="inventory")
    assert json.loads(pack["notes"][0].split("languages: ")[1]) == {"python": 1, "javascript": 1}


def test_inventory_skips_a_file_whose_stat_fails_and_counts_it(tmp_path, monkeypatch):
    """audit-331eefaf: a bare `continue` made the skip invisible.

    `omitted` is the mechanism that separates "this tree has no files" from
    "we could not read them", and an empty `{}` here reported the second as the
    first. Deleted-but-still-indexed paths reach this branch routinely, so it
    is not an edge case.
    """
    root = _repo(tmp_path, {"a.py": PY})
    real = Path.stat

    def flaky(self, **kw):
        if self.name == "a.py":
            raise OSError("gone")
        return real(self, **kw)

    monkeypatch.setattr(Path, "stat", flaky)
    pack = cp.build(root=root, goal="", mode="inventory")
    assert pack["files"] == []
    assert pack["omitted"]["files_unstatable"] == 1


def test_inventory_line_count_matches_the_file_exactly(tmp_path):
    """audit-9b0c282c: `count("\\n") + 1` was high by one for every normal file.

    Asserted as an equality against a known fixture. The previous test bounded
    it with `> 1`, which no off-by-one can fail — and the error was systematic
    rather than random, so it survived any averaging a caller did.
    """
    root = _repo(tmp_path, {"three.py": "a = 1\nb = 2\nc = 3\n", "noeol.py": "x = 1"})
    rows = {f["path"]: f for f in cp.build(root=root, goal="", mode="inventory")["files"]}
    assert rows["three.py"]["lines"] == 3
    assert rows["noeol.py"]["lines"] == 0  # no newline at all, so no line terminator


def test_line_count_returns_none_when_the_file_cannot_be_opened(tmp_path):
    """A directory entry that vanishes between listing and reading."""
    root = tmp_path.resolve()
    assert cp._line_count(root / "absent.py", root) is None


def test_symbols_returns_outlines_and_counts_unreadable_files(tmp_path):
    root = _repo(tmp_path, {"a.py": PY, "plain.txt": "no declarations here\n"})
    (root / "b.bin").write_bytes(b"\xff\xfe")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    pack = cp.build(root=root, goal="", mode="symbols")
    assert [row["path"] for row in pack["files"]] == ["a.py"]
    assert pack["omitted"]["files"] == 1
    assert {s["name"] for s in pack["files"][0]["symbols"]} == {"outer", "Thing", "method"}


def test_diff_returns_changed_hunks_with_the_enclosing_symbol(tmp_path):
    root = _repo(tmp_path, {"a.py": PY})
    (root / "a.py").write_text(PY.replace("return 1", "return 2"), encoding="utf-8")
    pack = cp.build(root=root, goal="", mode="diff")
    assert pack["candidates"]
    assert {c["symbol"] for c in pack["candidates"]} == {"method"}
    assert pack["notes"] == ["base: HEAD"]


def test_diff_marks_a_pure_deletion_and_never_emits_an_inverted_range(tmp_path):
    root = _repo(tmp_path, {"a.py": "one\ntwo\nthree\n"})
    (root / "a.py").write_text("one\nthree\n", encoding="utf-8")
    pack = cp.build(root=root, goal="", mode="diff")
    assert [list(c["reason"]) for c in pack["candidates"]] == [["deleted-lines"]]
    assert all(c["start"] <= c["end"] for c in pack["candidates"])


def test_diff_never_attributes_a_deleted_files_hunk_to_another_file(tmp_path):
    """audit-497790b7: `+++ /dev/null` left `current` on the previous entry.

    A deleted file's hunks were emitted as candidates on whichever file's
    `+++` header preceded them — on this repo's own tree, four deleted findings
    files all surfaced as `INDEX.md:1-1` — and the deletion itself produced no
    candidate at all. A reviewer sent to the cited range read an untouched
    line, so the pack's coordinates were worse than absent.
    """
    root = _repo(tmp_path, {"a_keep.py": PY, "b_gone.py": "def goner():\n    return 2\n"})
    (root / "b_gone.py").unlink()
    (root / "a_keep.py").write_text(PY.replace("return 1", "return 99"), encoding="utf-8")

    pack = cp.build(root=root, goal="", mode="diff")
    by_path: dict[str, list[dict]] = {}
    for candidate in pack["candidates"]:
        by_path.setdefault(candidate["path"], []).append(candidate)

    assert set(by_path) == {"a_keep.py", "b_gone.py"}
    assert [list(c["reason"]) for c in by_path["b_gone.py"]] == [["deleted-file"]]
    assert all("deleted" not in r for c in by_path["a_keep.py"] for r in c["reason"])


def test_diff_ignores_a_content_line_that_looks_like_a_file_header(tmp_path):
    """An added line reading `++ b/x` renders as `+++ b/x` in the diff.

    Same root cause as the deleted-file case: without an anchor on
    `diff --git`, repository *content* could name the file that subsequent
    hunks were attributed to. This repo's own docs quote diffs, so the shape is
    present rather than hypothetical.
    """
    root = _repo(tmp_path, {"doc.md": "intro\n"})
    (root / "doc.md").write_text("intro\n++ b/etc/passwd\n", encoding="utf-8")
    pack = cp.build(root=root, goal="", mode="diff")
    assert {c["path"] for c in pack["candidates"]} == {"doc.md"}


def test_diff_parses_hunks_under_a_mnemonic_prefix_config(tmp_path):
    """A user with `diff.mnemonicPrefix` gets c/ and w/, not a/ and b/.

    A parser keyed to `+++ b/` returns zero hunks on their machine and reports a
    changed tree as unchanged — silently, which is why this is pinned.
    """
    root = _repo(tmp_path, {"a.py": PY})
    subprocess.run(["git", "config", "diff.mnemonicPrefix", "true"], cwd=root, check=True)
    (root / "a.py").write_text(PY.replace("return 1", "return 2"), encoding="utf-8")
    assert cp.build(root=root, goal="", mode="diff")["candidates"]


def test_diff_ignores_a_hunk_in_a_file_outside_the_requested_paths(tmp_path):
    root = _repo(tmp_path, {"a.py": PY, "sub/b.py": PY})
    (root / "a.py").write_text(PY + "\nextra = 1\n", encoding="utf-8")
    (root / "sub" / "b.py").write_text(PY + "\nextra = 1\n", encoding="utf-8")
    pack = cp.build(root=root, goal="", mode="diff", paths=["sub"])
    assert {c["path"] for c in pack["candidates"]} == {"sub/b.py"}


def test_evidence_returns_ranges_snapped_to_the_enclosing_symbol(tmp_path):
    root = _repo(tmp_path, {"a.py": PY})
    pack = cp.build(root=root, goal="subprocess_call", mode="evidence", budget_tokens=4000)
    assert pack["candidates"]
    top = pack["candidates"][0]
    assert top["symbol"] == "outer"
    assert top["start"] == 4 and top["end"] == 6
    assert list(top["reason"]) == ["subprocess_call"]


def test_evidence_snaps_to_a_later_symbol_not_the_first_in_the_outline(tmp_path):
    """The range walk must skip past earlier declarations, not stop at the first."""
    root = _repo(tmp_path, {"a.py": PY})
    pack = cp.build(root=root, goal="method", mode="evidence")
    top = next(c for c in pack["candidates"] if c["path"] == "a.py")
    assert top["symbol"] == "method"
    assert top["start"] == 10


def test_evidence_falls_back_to_a_window_when_no_symbol_encloses_the_line(tmp_path):
    root = _repo(tmp_path, {"top.py": "TARGET = 1\n"})
    pack = cp.build(root=root, goal="target", mode="evidence")
    assert pack["candidates"][0]["symbol"] == ""
    assert pack["candidates"][0]["start"] == 1


def test_evidence_merges_overlapping_matches_in_one_file(tmp_path):
    body = "def f():\n    alpha = 1\n    alpha = 2\n    alpha = 3\n"
    root = _repo(tmp_path, {"a.py": body})
    pack = cp.build(root=root, goal="alpha", mode="evidence")
    hits = [c for c in pack["candidates"] if c["path"] == "a.py"]
    assert len(hits) == 1
    assert hits[0]["score"] == 3.0


def test_evidence_stops_at_the_budget_and_says_how_many_it_left(tmp_path):
    filler = "\n".join(f"    padding_line_{n} = {n}" for n in range(30))
    files = {f"f{i}.py": f"def f{i}():\n{filler}\n    return TARGET\n" for i in range(20)}
    root = _repo(tmp_path, files)
    pack = cp.build(root=root, goal="target", mode="evidence", budget_tokens=256)
    assert pack["budget"]["estimated"] <= 256
    assert pack["omitted"]["candidates_over_budget"] > 0


def test_evidence_reports_scanned_unmatched_and_unreadable_counts(tmp_path):
    root = _repo(tmp_path, {"hit.py": "TARGET = 1\n", "miss.py": "other = 2\n"})
    (root / "b.bin").write_bytes(b"\xff\xfe")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    omitted = cp.build(root=root, goal="target", mode="evidence")["omitted"]
    assert omitted["files_scanned"] == 3
    assert omitted["files_unmatched"] == 1
    assert omitted["files_unreadable"] == 1
    assert omitted["terms"] == ["target"]


def test_evidence_rejects_a_goal_with_no_searchable_term(tmp_path):
    root = _repo(tmp_path, {"a.py": PY})
    with pytest.raises(cp.PackError, match="no searchable term"):
        cp.build(root=root, goal="the and for", mode="evidence")


# ── constructs: defect classes whose signature is punctuation ─────────────────
#
# `_WORD` needs three characters, so `as`, `!` and `==` carry no term a goal can
# match. The whole family was unreachable by evidence mode, and a lens driven by
# a pack over a large repository never received those lines and reported clean.

_TS_CAST = """export interface User {
  id: string;
}

export async function fetchUser(url: string): Promise<User> {
  const body = await fetchRaw(url);
  return body as User;
}
"""


def test_a_construct_reaches_a_defect_with_no_lexical_signature(tmp_path):
    """The case the finding was filed on: an unsound cast is two characters.

    Every term of a class-written goal ("unchecked cast assertion untyped
    boundary") appears nowhere in the file — the match has to come from the
    operator, or not at all.
    """
    root = _repo(tmp_path, {"api.ts": _TS_CAST})
    pack = cp.build(root=root, goal="unchecked cast assertion untyped boundary", mode="evidence")
    hits = [c for c in pack["candidates"] if "unsound-cast" in c["reason"]]
    assert hits, "the cast was not reached"
    assert any(c["start"] <= 7 <= c["end"] for c in hits)


def test_a_goal_that_names_no_construct_packs_what_it_always_did(tmp_path):
    """Constructs activate by being NAMED. Nothing turns on by itself.

    Without this the cast pattern would fire on every TypeScript file in every
    pack, and `loose-equality` alone would match most of a JavaScript one.
    """
    root = _repo(tmp_path, {"api.ts": _TS_CAST})
    pack = cp.build(root=root, goal="fetchUser promise interface", mode="evidence")
    assert not any("unsound-cast" in c["reason"] for c in pack["candidates"])


def test_a_construct_is_scoped_to_the_languages_it_means_something_in(tmp_path):
    """`as` is a cast in TypeScript and an import in Python.

    Hunting the TypeScript shape in a Python file is how a construct scan turns
    into noise that outranks the real evidence.
    """
    root = _repo(tmp_path, {"mod.py": "import json as j\n\nwith open('f') as fh:\n    pass\n"})
    pack = cp.build(root=root, goal="unchecked cast assertion", mode="evidence")
    assert not any("unsound-cast" in c["reason"] for c in pack["candidates"])


@pytest.mark.parametrize(
    "line,construct,matches",
    [
        # `as const` narrows rather than widens — the one spelling of this
        # operator that asserts nothing.
        ("const x = {a: 1} as const;", "unsound-cast", False),
        ("return body as User;", "unsound-cast", True),
        # a lowercase target is a variable, not a type
        ("const y = as_user;", "unsound-cast", False),
        ("const v = user!.name;", "non-null-assertion", True),
        ("if (!user) return;", "non-null-assertion", False),
        ("if (a != b) return;", "non-null-assertion", False),
        ("if (a == b) return;", "loose-equality", True),
        ("if (a === b) return;", "loose-equality", False),
        ("if (a !== b) return;", "loose-equality", False),
        ("if (a <= b) return;", "loose-equality", False),
        ("const f = () => x;", "loose-equality", False),
    ],
)
def test_construct_patterns_match_the_shape_and_not_its_neighbours(line, construct, matches):
    """Each near-miss here is a spelling the pattern must NOT claim.

    A construct scan earns its place only if it separates the defect from the
    punctuation next to it: `===` from `==`, a negation from an assertion, a
    narrowing `as const` from a widening cast.
    """
    _aliases, _languages, pattern = cp._CONSTRUCTS[construct]
    assert bool(pattern.search(line)) is matches


def test_active_constructs_needs_both_an_alias_and_the_language():
    """Two independent gates, so both are asserted separately."""
    assert cp._active_constructs({"cast"}, "typescript")
    assert not cp._active_constructs({"cast"}, "python")
    assert not cp._active_constructs({"unrelated"}, "typescript")


def test_changed_only_narrows_every_mode_not_just_diff(tmp_path):
    root = _repo(tmp_path, {"a.py": "TARGET = 1\n", "b.py": "TARGET = 2\n"})
    (root / "a.py").write_text("TARGET = 3\n", encoding="utf-8")
    pack = cp.build(root=root, goal="target", mode="evidence", changed_only=True)
    assert {c["path"] for c in pack["candidates"]} == {"a.py"}


# ── hostile input ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("mode", ["diff", "evidence"])
def test_a_base_beginning_with_a_dash_is_refused_before_it_reaches_git(tmp_path, mode):
    """git reads any leading-dash argument as an option, and `git diff` can write files.

    A probe passing `--base=--output=<path>` made git create that file. `base`
    comes from wherever the caller got it — a branch name, a PR base ref, free
    text after the command — so this is reachable from untrusted input.
    """
    root = _repo(tmp_path, {"a.py": PY})
    sentinel = tmp_path / "pwned.txt"
    with pytest.raises(cp.PackError, match="must name a revision, not an option"):
        cp.build(root=root, goal="outer", mode=mode, base=f"--output={sentinel}")
    assert not sentinel.exists()


def test_an_empty_base_is_refused(tmp_path):
    root = _repo(tmp_path, {"a.py": PY})
    with pytest.raises(cp.PackError, match="must name a revision"):
        cp.build(root=root, goal="outer", mode="diff", base="")


def test_a_symlink_escaping_the_repo_is_not_read(tmp_path):
    """An audited tree may be hostile — `skill-safety` and `deps` exist for that.

    A tracked symlink to a file outside the repository would otherwise have its
    contents ranked, ranged and returned under an in-repo path, where a
    plausible-looking path draws no attention.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("SUPERSECRET value\n", encoding="utf-8")
    root = _repo(tmp_path / "repo", {"real.py": "harmless = 1\n"})
    (root / "link.py").symlink_to(outside / "secret.txt")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)

    pack = cp.build(root=root, goal="supersecret", mode="evidence")
    assert pack["candidates"] == []
    assert "SUPERSECRET" not in json.dumps(pack)
    # It is skipped, not hidden: the count keeps the omission visible.
    assert pack["omitted"]["files_unreadable"] == 1


def test_a_symlink_escaping_the_repo_is_not_read_by_any_mode(tmp_path):
    """`_read` is the single choke point, so the guard must hold for every mode."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("def leaked():\n    pass\n", encoding="utf-8")
    root = _repo(tmp_path / "repo", {"real.py": "harmless = 1\n"})
    (root / "link.py").symlink_to(outside / "secret.txt")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)

    outlined = {f["path"] for f in cp.build(root=root, goal="", mode="symbols")["files"]}
    assert "link.py" not in outlined
    pack = cp.build(root=root, goal="", mode="inventory")
    rows = {f["path"]: f for f in pack["files"]}
    # Listed, never read. `None` rather than `0`: a refused read has to be
    # distinguishable from an empty file, or a caller cannot tell "we did not
    # look at this" from "there was nothing here".
    assert rows["link.py"]["lines"] is None
    assert pack["omitted"]["files_unreadable"] == 1
    assert "def leaked" not in json.dumps(pack)


def test_a_utf8_bom_does_not_erase_a_files_outline(tmp_path):
    """An empty outline is indistinguishable from a file with no declarations.

    A BOM left in place makes `ast.parse` raise and stops the regex fallback's
    `^\\s*` matching, so the file reported zero symbols and a lens would skip it
    believing it held nothing. BOMs are routine from Windows editors.
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "bom.py").write_bytes(b"\xef\xbb\xbfdef alpha():\r\n    return TARGET\r\n")
    pack = cp.build(root=root, goal="", mode="symbols")
    assert [s["name"] for f in pack["files"] for s in f["symbols"]] == ["alpha"]


def test_a_repository_with_no_commits_still_answers_the_non_diff_modes(tmp_path):
    root = _repo(tmp_path, {"a.py": PY}, commit=False)
    for mode in ("inventory", "symbols", "evidence"):
        assert cp.build(root=root, goal="outer method", mode=mode) is not None
    with pytest.raises(cp.PackError, match="git diff"):
        cp.build(root=root, goal="outer", mode="diff")


def test_a_pathological_match_count_still_respects_the_budget(tmp_path):
    """One term on 20k lines must not blow the budget or the wall clock."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "big.py").write_text("TARGET = 1\n" * 20_000, encoding="utf-8")
    pack = cp.build(root=root, goal="target", mode="evidence", budget_tokens=2000)
    assert pack["budget"]["estimated"] <= 2000


# ── contract ─────────────────────────────────────────────────────────────────


def test_every_mode_carries_the_verification_reminder(tmp_path):
    root = _repo(tmp_path, {"a.py": PY})
    for mode in cp.MODES:
        pack = cp.build(root=root, goal="outer", mode=mode)
        assert "Re-read the original source" in pack["verification"]


def test_build_rejects_an_unknown_mode_naming_the_valid_set(tmp_path):
    with pytest.raises(cp.PackError, match="inventory, symbols, diff, evidence"):
        cp.build(root=tmp_path, goal="", mode="minify")


def test_build_rejects_a_budget_below_the_floor(tmp_path):
    with pytest.raises(cp.PackError, match="at least 256"):
        cp.build(root=tmp_path, goal="x", mode="evidence", budget_tokens=10)


def test_build_rejects_a_root_that_is_not_a_directory(tmp_path):
    target = tmp_path / "file"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(cp.PackError, match="not a directory"):
        cp.build(root=target, goal="", mode="inventory")


def test_self_test_passes_on_a_real_repository(tmp_path):
    root = _repo(tmp_path, {"a.py": PY})
    result = cp.self_test(root)
    assert result["passed"] is True
    assert {c["control"] for c in result["checks"]} == {
        "symbols-of-self",
        "evidence-returns-candidates",
        "inventory-lists-root",
    }


def test_self_test_fails_when_the_root_yields_nothing(tmp_path):
    """An empty pack must report as a broken retriever, never as a clean scan."""
    result = cp.self_test(_repo(tmp_path, {}, commit=False))
    assert result["passed"] is False
    assert [c["passed"] for c in result["checks"] if c["control"] == "inventory-lists-root"] == [
        False
    ]


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_cli_prints_compact_json_and_exits_zero(tmp_path, capsys):
    root = _repo(tmp_path, {"a.py": PY})
    assert cp.main(["--root", str(root), "--mode", "inventory"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1  # compact: one trailing newline, no indentation
    assert json.loads(out)["mode"] == "inventory"


def test_cli_self_test_exit_code_tracks_the_controls(tmp_path, capsys):
    passing = _repo(tmp_path / "ok", {"a.py": PY})
    assert cp.main(["--root", str(passing), "--self-test"]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True
    empty = _repo(tmp_path / "empty", {}, commit=False)
    assert cp.main(["--root", str(empty), "--self-test"]) == 1


def test_cli_usage_error_exits_two_and_explains_on_stderr(tmp_path, capsys):
    assert cp.main(["--root", str(tmp_path), "--mode", "evidence", "--goal", "the"]) == 2
    assert "no searchable term" in capsys.readouterr().err


def test_git_timeout_is_an_environment_error_not_a_usage_error(tmp_path, monkeypatch):
    """reliability-4bcfa272: `_git` ran unbounded, so a hung git hung the caller.

    `mcp_server` is a single-threaded stdio loop, so one wedged git stalled
    every later tool call — and a call that never returns is never recorded as
    "errored" by the preflight rule either. The bound has to raise the
    *environment* class: nothing about the arguments was wrong, so an agent
    told to fix them retries forever.
    """

    def hang(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=cp.GIT_TIMEOUT)

    monkeypatch.setattr(cp.subprocess, "run", hang)
    with pytest.raises(cp.PackEnvironmentError, match="timed out"):
        cp._git(tmp_path, "status")


def test_a_broken_git_exits_one_while_a_bad_argument_exits_two(tmp_path, capsys, monkeypatch):
    """audit-02e25f35: both reported as 2, the documented usage code.

    The exit code is what an agent branches on. Collapsed onto 2, a host with
    no git read as "your arguments were wrong", so the agent retried argument
    variations instead of recording the tool as unavailable.
    """
    root = _repo(tmp_path, {"a.py": PY})

    def absent(*_a, **_k):
        raise OSError("No such file or directory: 'git'")

    monkeypatch.setattr(cp.subprocess, "run", absent)
    assert cp.main(["--root", str(root), "--mode", "diff"]) == 1
    assert "git is not available" in capsys.readouterr().err

    monkeypatch.undo()
    assert cp.main(["--root", str(root), "--mode", "evidence", "--goal", ""]) == 2


def test_merging_two_ranges_sums_their_estimates(tmp_path):
    """audit-2635df3b: `max` under-counted a range wider than either input.

    A no-symbol window (line ±8) overlapping a symbol's span widens the merged
    range, so carrying one input's estimate let `_pack_to_budget` report having
    spent less than it did — and `budget.estimated` is what a caller reads to
    decide whether to widen.
    """
    left = cp.Candidate(path="a.py", start=1, end=13, score=1.0, reason=("x",), tokens=40)
    right = cp.Candidate(path="a.py", start=10, end=50, score=1.0, reason=("y",), tokens=120)
    merged = cp._merge([left, right])
    assert len(merged) == 1
    assert (merged[0].start, merged[0].end) == (1, 50)
    assert merged[0].tokens == 160  # summed: never below what the span costs


def test_cli_io_error_exits_one(tmp_path, capsys, monkeypatch):
    def boom(**_kw):
        raise OSError("disk gone")

    monkeypatch.setattr(cp, "build", boom)
    assert cp.main(["--root", str(tmp_path), "--mode", "inventory"]) == 1
    assert "disk gone" in capsys.readouterr().err


def test_cli_help_prints_usage_at_exit_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cp.main(["--help"])
    assert exc.value.code == 0
    assert "context-pack" in capsys.readouterr().out


def test_module_runs_as_a_script(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["context_pack.py", "--root", str(tmp_path), "--mode", "inventory"]
    )
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(cp.__file__)), run_name="__main__")
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "inventory"
