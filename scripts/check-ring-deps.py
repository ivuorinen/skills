#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Print this repo's complete module dependency graph and enforce the ring rule.

Three rings, innermost first. The rule is that an arrow never points outward:

    skills/*/scripts   (shipped, stdlib-only)   <- may not depend on anything below
    scripts            (internal dev tooling)   <- may depend on shipped
    scripts/hooks      (harness hooks)          <- may depend on either

An ordinary `import` is visible to every tool that reads Python. Some edges here
are not: a module whose filename contains a hyphen (`check-rules-anatomy.py`,
`process-sarif.py`) cannot be reached by `import`, because a hyphen is not valid
in an identifier, and renaming it would break every documented invocation. Those
modules are loaded through `importlib.util.spec_from_file_location` with the path
built from string literals — which means the edge exists at runtime and appears
in no import graph. An architecture check that reads only `import` statements
reports a graph missing exactly those edges, and reports it as complete.

This tool resolves both kinds and prints them together, marking which is which.
The visibility is the point: `--check` exits non-zero on a violation, but the
default listing is what makes a string-path edge as readable as an import.

Two shapes of string-path load are resolved:

  literal   `spec_from_file_location(name, Path(__file__).parent.parent / "a" / "b.py")`
            Every path segment is a string constant, so the target resolves to a
            real file and the edge is exact.

  sibling   `spec_from_file_location(stem, Path(__file__).resolve().parent / f"{stem}.py")`
            The filename is computed, but the directory is provably the loading
            module's own: the expression is anchored at `__file__`, walks only
            `.parent`, and contains no "..". Such an edge cannot leave its own
            directory, so it cannot cross a ring, and is reported as intra-ring
            without naming a specific file.

A `spec_from_file_location` call matching neither shape is an error: it is an
unresolvable edge, and passing it over would restore the silence this exists to
remove. Subprocess calls are deliberately not edges — a hook that shells out to
a validator crosses a process boundary, not an import boundary, and nothing is
loaded into the caller.

Exit codes: 0 success, 1 a violation or an unresolvable load, 2 usage error.
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Innermost first. The index is the ring's rank: an edge from rank i to rank j
# is legal only when j <= i.
RINGS: tuple[tuple[str, str], ...] = (
    ("shipped", "skills/*/scripts/*.py"),
    ("internal", "scripts/*.py"),
    ("hooks", "scripts/hooks/*.py"),
)


class UsageError(Exception):
    """Bad invocation — exit 2, distinct from a failed check."""


@dataclass
class Edge:
    src: str
    dst: str
    kind: str  # "import" | "path" | "path-sibling"

    def render(self) -> str:
        mark = {
            "import": "",
            "path": "  [string-path load]",
            "path-sibling": "  [string-path load, own directory]",
        }
        return f"  {self.src} -> {self.dst}{mark[self.kind]}"


@dataclass
class Graph:
    modules: dict[str, str] = field(default_factory=dict)  # relpath -> ring
    by_stem: dict[str, str] = field(default_factory=dict)  # importable stem -> relpath
    edges: list[Edge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def collect_modules(root: Path) -> Graph:
    """Every .py file in a ring, indexed by relative path and by import stem."""
    g = Graph()
    for ring, pattern in RINGS:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root).as_posix()
            # scripts/*.py also matches nothing under hooks/ (glob is not
            # recursive), so a file lands in exactly one ring.
            g.modules[rel] = ring
            # A hyphen-named file is not importable; it is reachable only by
            # path, which is the whole reason this tool exists.
            if "-" not in path.stem:
                g.by_stem.setdefault(path.stem, rel)
    if not g.modules:
        raise UsageError(f"no modules matched any ring pattern under {root} — the globs are stale")
    return g


def _literal_path_segments(node: ast.expr) -> list[str] | None:
    """String constants in a `Path(...) / "a" / "b.py"` chain, in order.

    Returns None when the expression contains a non-literal segment.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _literal_path_segments(node.left)
        right = _literal_path_segments(node.right)
        if left is None or right is None:
            return None
        return left + right
    # `Path(__file__).parent...` anchors the chain; it contributes no segment.
    if isinstance(node, (ast.Call, ast.Attribute, ast.Name)):
        return []
    return None


def _anchored_at_own_dir(node: ast.expr) -> bool:
    """Whether the path expression provably stays in the loading module's dir.

    True when it is built from `__file__` using only attribute access (.parent,
    .resolve) with no ".." segment and no upward navigation beyond the first
    `.parent`. Such a path cannot reach another ring.
    """
    src = ast.dump(node)
    if "__file__" not in src or ".." in ast.unparse(node):
        return False
    # More than one `.parent` walks upward out of the module's own directory.
    return ast.unparse(node).count(".parent") <= 1


def _resolve_target(root: Path, module_path: Path, segments: list[str]) -> str | None:
    """Relative path of the file a literal segment chain names, if it exists."""
    if not segments or not segments[-1].endswith(".py"):
        return None
    # `Path(__file__).parent.parent / "a" / "b.py"` drops its `.parent` steps
    # when the segments are collected, so the anchor is unknown: try the module's
    # own directory and each ancestor. The search stops at the repository root —
    # a match found above it would name a file this repo does not contain.
    candidates = [
        base
        for base in (module_path.parent, *module_path.parents)
        if base == root or root in base.parents
    ]
    for base in candidates:
        candidate = base.joinpath(*segments)
        if candidate.is_file():
            try:
                return candidate.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                # A `..` segment or a symlink walked back out of the tree.
                return None
    return None


_SCOPE = (ast.FunctionDef, ast.AsyncFunctionDef)


def _walk_scope(node: ast.AST):
    """Descendants of `node` that belong to its own scope.

    Stops at a nested function, so a name assigned in one function is not
    mistaken for the same name assigned in a sibling. `mcp_server.py` binds
    `path` in two different functions; walking the module flat reports that as
    an ambiguous assignment and resolves neither.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPE):
            continue
        yield child
        yield from _walk_scope(child)


def _assignments(scope: ast.AST) -> dict[str, ast.expr | None]:
    """name -> the expression assigned to it within this one scope.

    Every real string-path load in this repo binds the path to a variable first
    (`_FINDINGS_PATH = Path(...) / "..."`, then `spec_from_file_location(n, _FINDINGS_PATH)`),
    so without this the call site is a bare Name and nothing resolves.

    A name assigned more than once maps to None: which value reaches the call is
    a question this tool cannot answer, and answering it wrongly would print a
    confident edge to the wrong file.
    """
    found: dict[str, ast.expr | None] = {}
    for node in _walk_scope(scope):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and node.value is not None:
                found[target.id] = None if target.id in found else node.value
    return found


def _path_load_calls(scope: ast.AST) -> list[ast.Call]:
    calls = []
    for node in _walk_scope(scope):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name == "spec_from_file_location":
            calls.append(node)
    return calls


def _import_edges(tree: ast.AST, g: Graph, rel: str) -> None:
    """Module-level and function-local `import` edges to another ring module."""
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module.split(".")[0]]
        for stem in names:
            dst = g.by_stem.get(stem)
            if dst and dst != rel:
                g.edges.append(Edge(rel, dst, "import"))


def _path_edges(tree: ast.AST, g: Graph, rel: str, root: Path, path: Path) -> None:
    """Edges from `spec_from_file_location` loads — the ones no import graph sees."""
    module_names = _assignments(tree)
    scopes: list[ast.AST] = [tree, *(n for n in ast.walk(tree) if isinstance(n, _SCOPE))]
    for scope in scopes:
        local_names = module_names if scope is tree else _assignments(scope)
        for call in _path_load_calls(scope):
            _one_path_edge(call, g, rel, root, path, local_names, module_names)


def _one_path_edge(
    call: ast.Call,
    g: Graph,
    rel: str,
    root: Path,
    path: Path,
    local_names: dict[str, ast.expr | None],
    module_names: dict[str, ast.expr | None],
) -> None:
    if len(call.args) < 2:
        g.errors.append(f"{rel}: spec_from_file_location with no path argument")
        return
    expr = call.args[1]
    if isinstance(expr, ast.Name):
        # Function scope shadows module scope, as Python does.
        scope_used = local_names if expr.id in local_names else module_names
        if expr.id in scope_used:
            bound = scope_used[expr.id]
            if bound is None:
                g.errors.append(
                    f"{rel}: string-path load reads {expr.id!r}, which is assigned more "
                    f"than once in its scope — the target cannot be determined statically"
                )
                return
            expr = bound
    segments = _literal_path_segments(expr)
    if segments:
        dst = _resolve_target(root, path, segments)
        if dst is None:
            g.errors.append(
                f"{rel}: string-path load resolves to no file on disk: {'/'.join(segments)}"
            )
        elif dst != rel:
            g.edges.append(Edge(rel, dst, "path"))
    elif _anchored_at_own_dir(expr):
        g.edges.append(Edge(rel, f"{Path(rel).parent.as_posix()}/*", "path-sibling"))
    else:
        g.errors.append(
            f"{rel}: string-path load is not statically resolvable and is not "
            f"provably in its own directory: {ast.unparse(expr)}"
        )


def build(root: Path) -> Graph:
    g = collect_modules(root)
    for rel, _ring in g.modules.items():
        path = root / rel
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            # An unparseable module is unscanned code. Reporting the rest as
            # clean would hide exactly the edge this tool exists to surface.
            g.errors.append(f"{rel}: cannot parse ({exc})")
            continue
        _import_edges(tree, g, rel)
        _path_edges(tree, g, rel, root, path)
    # Deduplicate while keeping order; a module importing the same target from
    # two functions is one edge, not two.
    seen: set[tuple[str, str, str]] = set()
    unique: list[Edge] = []
    for e in g.edges:
        key = (e.src, e.dst, e.kind)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    g.edges = unique
    return g


def violations(g: Graph) -> list[str]:
    """Edges pointing outward — an inner ring depending on an outer one."""
    rank = {name: i for i, (name, _) in enumerate(RINGS)}
    out: list[str] = []
    for e in g.edges:
        if e.kind == "path-sibling":
            continue  # cannot leave its own directory, so cannot cross a ring
        src_ring = g.modules.get(e.src)
        dst_ring = g.modules.get(e.dst)
        if src_ring is None or dst_ring is None:
            continue
        if rank[dst_ring] > rank[src_ring]:
            out.append(
                f"  {e.src} ({src_ring}) -> {e.dst} ({dst_ring}): "
                f"a {src_ring} module must not depend on {dst_ring}"
            )
    return out


def render(g: Graph) -> str:
    lines: list[str] = []
    for ring, _ in RINGS:
        members = [e for e in g.edges if g.modules.get(e.src) == ring]
        lines.append(f"{ring}:")
        lines.extend(e.render() for e in members) if members else lines.append("  (no edges)")
    counts = {k: sum(1 for e in g.edges if e.kind == k) for k in ("import", "path", "path-sibling")}
    lines.append("")
    lines.append(
        f"{len(g.modules)} modules, {len(g.edges)} edges "
        f"({counts['import']} import, {counts['path']} string-path, "
        f"{counts['path-sibling']} string-path own-directory)"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("root", nargs="?", default=".", help="repository root (default: .)")
    parser.add_argument(
        "--check", action="store_true", help="exit 1 on a ring violation or unresolvable load"
    )
    args = parser.parse_args(argv)

    try:
        root = Path(args.root).resolve()
        if not root.is_dir():
            raise UsageError(f"not a directory: {args.root}")
        g = build(root)
    except UsageError as exc:
        print(f"ERROR  {exc}", file=sys.stderr)
        return 2

    print(render(g))

    bad = violations(g)
    if g.errors:
        print("\nUnresolvable module loads:", file=sys.stderr)
        for e in g.errors:
            print(f"  {e}", file=sys.stderr)
    if bad:
        print("\nRing violations:", file=sys.stderr)
        for b in bad:
            print(b, file=sys.stderr)

    if args.check and (bad or g.errors):
        return 1
    if args.check:
        print("\nOK  ring rule holds; every module load resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
