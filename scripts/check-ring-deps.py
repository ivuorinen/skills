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

A string-path load is any call in `_PATH_LOADERS` — `spec_from_file_location`,
`importlib.machinery.SourceFileLoader` and its sourceless sibling,
`runpy.run_path` — spelled directly or through an alias, with its path argument
optionally wrapped in `str()`/`os.fspath()`. The hook that loads findings.py
uses SourceFileLoader, and that edge was missing until the table held it
(arch-548ae822). Two shapes of path argument are resolved:

  literal   `spec_from_file_location(name, Path(__file__).parent.parent / "a" / "b.py")`
            Every path segment is a string constant, or a name bound once to
            one, so the target resolves to a real file and the edge is exact.
            Only the leftmost anchor may contribute no segment (audit-60098599).

  sibling   `spec_from_file_location(stem, Path(__file__).resolve().parent / f"{stem}.py")`
            The filename is computed, but the directory is provably the loading
            module's own: the expression is exactly `Path(__file__)`, an
            optional `.resolve()`, one `.parent`, then `/` and an f-string whose
            literal text holds no separator and no "..". Such an edge cannot
            leave its own directory, so it cannot cross a ring, and is reported
            as intra-ring without naming a specific file.

A path-loader call matching neither shape is an error: it is an
unresolvable edge, and passing it over would restore the silence this exists to
remove. The sibling shape is matched on the AST, not on text: a substring test
read `.parents[3]` and an `os.path.dirname` chain as own-directory and passed
both across rings (audit-7d8bf871). Its ceiling is the interpolated value — a
`{stem}` holding "../x" at runtime is not something static analysis can see.
Subprocess calls are deliberately not edges — a hook that shells out to
a validator crosses a process boundary, not an import boundary, and nothing is
loaded into the caller.

A dynamic import — `importlib.import_module(...)` or `__import__(...)` — is an
edge too, marked as one. Its argument resolves when it is a string literal, a
name bound once to one, or a subscript of a name bound once to a dict of string
literals; anything else is an unresolvable load. A call reached through an alias
(`imp = importlib.import_module`) is not recognised as a dynamic import.

A dotted import (`from scripts.hooks import x`, `import scripts.hooks.x`) is
resolved against its full path, from the importing module's directory and from
the repository root. A relative import (`from .hooks import x`) resolves
against the importing file's directory, and one that names no file in the
repository is an unresolvable load (audit-1e187e32). Ring globs are recursive,
and an edge to a file outside every ring is reported rather than skipped: it is
a dependency the rule cannot rank, which is not the same as one that obeys it.

Exit codes: 0 success, 1 a violation or an unresolvable load, 2 usage error.
"""

from __future__ import annotations

import argparse
import ast
import enum
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

# Innermost first. The index is the ring's rank: an edge from rank i to rank j
# is legal only when j <= i.
RINGS: tuple[tuple[str, str], ...] = (
    ("shipped", "skills/*/scripts/**/*.py"),
    ("internal", "scripts/**/*.py"),
    ("hooks", "scripts/hooks/**/*.py"),
)


class UsageError(Exception):
    """Bad invocation — exit 2, distinct from a failed check."""


@dataclass
class Edge:
    src: str
    dst: str
    kind: str  # "import" | "dynamic" | "path" | "path-sibling"

    def render(self) -> str:
        mark = {
            "import": "",
            "dynamic": "  [dynamic import]",
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
            # scripts/**/*.py also matches scripts/hooks/; the hooks ring comes
            # later in RINGS and overwrites, so a file lands in exactly one ring.
            g.modules[rel] = ring
            # A hyphen-named file is not importable; it is reachable only by
            # path, which is the whole reason this tool exists.
            if "-" not in path.stem:
                g.by_stem.setdefault(path.stem, rel)
    if not g.modules:
        raise UsageError(f"no modules matched any ring pattern under {root} — the globs are stale")
    return g


class _Unbound(enum.Enum):
    """A name no scope assigns — distinct from None, which means "assigned twice"."""

    TOKEN = 0


_UNBOUND: Final = _Unbound.TOKEN

# name -> the expression bound to it, None if assigned more than once, or
# _UNBOUND if no scope in view assigns it.
Lookup = Callable[[str], "ast.expr | _Unbound | None"]


def _literal_path_segments(
    node: ast.expr,
    lookup: Lookup | None = None,
    anchor: bool = True,
    _seen: frozenset[str] = frozenset(),
) -> list[str] | None:
    """String constants in a `Path(...) / "a" / "b.py"` chain, in order.

    Returns None when the expression contains a non-literal segment.

    Only the leftmost operand — the anchor, `Path(__file__).parent...` or an
    imported root such as `SHIPPED_ROOT` — may contribute no segment. Every
    operand to its right must be a string constant, or a name `lookup` finds
    bound once to one (`HOOKS = "../hooks"`). Dropping a Name segment there
    silently resolved `parent / HOOKS / "lib.py"` to the module's own `lib.py`
    (audit-60098599). An anchor that is itself a name bound once in scope is
    followed, so `BASE = parent / "sub"` keeps its `"sub"`; a name `lookup`
    cannot find (an import, a parameter) stays an anchor with no segment.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _literal_path_segments(node.left, lookup, anchor, _seen)
        right = _literal_path_segments(node.right, lookup, False, _seen)
        if left is None or right is None:
            return None
        return left + right
    bound = lookup(node.id) if lookup and isinstance(node, ast.Name) else _UNBOUND
    if not anchor:
        if isinstance(bound, ast.Constant) and isinstance(bound.value, str):
            return [bound.value]
        return None
    if isinstance(node, ast.Name) and bound is not _UNBOUND:
        # Assigned more than once, or a chain that refers back to itself.
        if bound is None or node.id in _seen:
            return None
        return _literal_path_segments(bound, lookup, True, _seen | {node.id})
    # `Path(__file__).parent...` anchors the chain; it contributes no segment.
    if isinstance(node, (ast.Call, ast.Attribute, ast.Name)):
        return []
    return None


def _anchored_at_own_dir(node: ast.expr) -> bool:
    """Whether the path expression provably stays in the loading module's dir.

    True only for `Path(__file__)[.resolve()].parent / f"..."` whose literal
    text holds no separator and no "..". Any other `__file__`-derived shape
    (`.parents[n]`, `os.path.dirname` chains, a second `.parent`) is False and
    so becomes an unresolvable-load error.
    """
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
        return False
    anchor, name = node.left, node.right
    if not (isinstance(anchor, ast.Attribute) and anchor.attr == "parent"):
        return False
    base = anchor.value
    if (
        isinstance(base, ast.Call)
        and isinstance(base.func, ast.Attribute)
        and base.func.attr == "resolve"
        and not base.args
    ):
        base = base.func.value
    is_file_path = (
        isinstance(base, ast.Call)
        and isinstance(base.func, ast.Name)
        and base.func.id == "Path"
        and len(base.args) == 1
        and isinstance(base.args[0], ast.Name)
        and base.args[0].id == "__file__"
    )
    if not (is_file_path and isinstance(name, ast.JoinedStr)):
        return False
    text = "".join(
        v.value for v in name.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
    )
    return not any(bad in text for bad in ("/", "\\", ".."))


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


# Every stdlib callable that executes a file named by a path, with the position
# and keyword of that path argument. Recognising only spec_from_file_location
# left `SourceFileLoader(name, path)` — the hook's load of findings.py — out of
# the graph, and let an outward load written that way pass (arch-548ae822).
_PATH_LOADERS: dict[str, tuple[int, str]] = {
    "spec_from_file_location": (1, "location"),
    "SourceFileLoader": (1, "path"),
    "SourcelessFileLoader": (1, "path"),
    "run_path": (0, "path_name"),
}


def _loader_aliases(tree: ast.AST) -> dict[str, str]:
    """Local name -> the path loader it is bound to.

    `from importlib.machinery import SourceFileLoader as L` and
    `L = importlib.machinery.SourceFileLoader` hide the loader's name at the
    call site. Ceiling: a loader passed as an argument or stored in a container
    is not followed.
    """
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name in _PATH_LOADERS:
                    found[a.asname or a.name] = a.name
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            v = node.value
            name = v.attr if isinstance(v, ast.Attribute) else getattr(v, "id", "")
            loader = name if name in _PATH_LOADERS else found.get(name)
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if loader and isinstance(t, ast.Name):
                    found[t.id] = loader
    return found


def _path_load_calls(scope: ast.AST, aliases: dict[str, str]) -> list[tuple[ast.Call, str]]:
    """(call, loader name) for each path-loader call in this one scope."""
    calls = []
    for node in _walk_scope(scope):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            loader = func.attr if func.attr in _PATH_LOADERS else None
        else:
            name = getattr(func, "id", "")
            loader = name if name in _PATH_LOADERS else aliases.get(name)
        if loader:
            calls.append((node, loader))
    return calls


def _dotted_target(root: Path, path: Path, dotted: str) -> str | None:
    """Relative path of the file a dotted name `a.b.c` names, if one exists.

    Tried from the importing module's own directory (sys.path[0] for a script)
    and from the repository root, as `a/b/c.py` and then `a/b/c/__init__.py`.
    """
    for base in (path.parent, root):
        stem = base.joinpath(*dotted.split("."))
        for candidate in (stem.with_name(stem.name + ".py"), stem / "__init__.py"):
            if candidate.is_file():
                return candidate.relative_to(root).as_posix()
    return None


def _import_edges(tree: ast.AST, g: Graph, rel: str, root: Path, path: Path) -> None:
    """Module-level and function-local `import` edges to another ring module.

    A plain name resolves by stem; a dotted one by its full path, so
    `from scripts.hooks import x` is the edge to `scripts/hooks/x.py` rather
    than a lookup of the stem `scripts`, which matched nothing (audit-7d8bf871).
    """
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            _relative_import_edges(node, g, rel, root, path)
            continue
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
        for name in names:
            if "." in name:
                dst = _dotted_target(root, path, name)
            else:
                dst = g.by_stem.get(name)
            if dst and dst != rel:
                g.edges.append(Edge(rel, dst, "import"))


def _module_file(stem: Path) -> Path | None:
    """`stem.py`, else `stem/__init__.py`, whichever exists."""
    for candidate in (stem.with_name(stem.name + ".py"), stem / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _relative_import_edges(
    node: ast.ImportFrom, g: Graph, rel: str, root: Path, path: Path
) -> None:
    """Edges from `from .x import y`, resolved against the importing file's package.

    Relative imports were skipped outright, so an outward `from .hooks import
    _hooklib` passed --check while `from hooks import _hooklib` failed it
    (audit-1e187e32). The base is the file's directory, up `level - 1`
    parents; the module and each imported name are tried as a file there.
    An imported name that is no file is an attribute and adds no edge, but an
    import where neither the module nor any name resolves inside the
    repository is an unresolvable load.
    """
    base = path.parent
    for _ in range(node.level - 1):
        base = base.parent
    found: list[Path] = []
    if base == root or root in base.parents:
        package = base.joinpath(*node.module.split(".")) if node.module else base
        module = _module_file(package) if node.module else _module_file(base / "__init__")
        found = [f for f in (module, *(_module_file(package / a.name) for a in node.names)) if f]
    if not found:
        g.errors.append(f"{rel}: relative import resolves to no module: {ast.unparse(node)}")
        return
    for f in found:
        dst = f.relative_to(root).as_posix()
        if dst != rel:
            g.edges.append(Edge(rel, dst, "import"))


_DYNAMIC_IMPORTERS = frozenset({"import_module", "__import__"})


def _dynamic_names(
    expr: ast.expr,
    local_names: dict[str, ast.expr | None],
    module_names: dict[str, ast.expr | None],
) -> list[str] | None:
    """Module names a dynamic import's first argument can hold, or None if unknowable.

    Resolved shapes: a string literal; a name bound once to one; and a subscript
    of a name bound once to a dict whose values are all string literals — the
    shape of pr_common's `import_module(_PROVIDER_MODULES[platform])`, where
    every value the key can select is on the page.
    """
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return [expr.value]
    if isinstance(expr, ast.Subscript):
        expr = expr.value
        subscripted = True
    else:
        subscripted = False
    if not isinstance(expr, ast.Name):
        return None
    scope_used = local_names if expr.id in local_names else module_names
    bound = scope_used.get(expr.id)
    if subscripted:
        if not isinstance(bound, ast.Dict):
            return None
        values = [
            v.value
            for v in bound.values
            if isinstance(v, ast.Constant) and isinstance(v.value, str)
        ]
        return values if len(values) == len(bound.values) else None
    if isinstance(bound, ast.Constant) and isinstance(bound.value, str):
        return [bound.value]
    return None


def _dynamic_import_edges(tree: ast.AST, g: Graph, rel: str, root: Path, path: Path) -> None:
    """Edges from `importlib.import_module(...)` and `__import__(...)` calls.

    Neither is an `ast.Import`, so an outward edge written as a dynamic import
    passed `--check` while the same edge as `import x` failed it
    (audit-0dac429b). A literal target resolves exactly as an import does; an
    argument that cannot be resolved statically is an unresolvable load, the
    same verdict a non-literal `spec_from_file_location` gets.
    """
    module_names = _assignments(tree)
    scopes: list[ast.AST] = [tree, *(n for n in ast.walk(tree) if isinstance(n, _SCOPE))]
    for scope in scopes:
        local_names = module_names if scope is tree else _assignments(scope)
        for node in _walk_scope(scope):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in _DYNAMIC_IMPORTERS:
                continue
            names = _dynamic_names(node.args[0], local_names, module_names) if node.args else None
            if names is None or any(n.startswith(".") for n in names):
                g.errors.append(
                    f"{rel}: dynamic import is not statically resolvable: {ast.unparse(node)}"
                )
                continue
            for target in names:
                dst = _dotted_target(root, path, target) if "." in target else g.by_stem.get(target)
                if dst and dst != rel:
                    g.edges.append(Edge(rel, dst, "dynamic"))


def _path_edges(tree: ast.AST, g: Graph, rel: str, root: Path, path: Path) -> None:
    """Edges from path-loader calls (`_PATH_LOADERS`) — the ones no import graph sees."""
    module_names = _assignments(tree)
    aliases = _loader_aliases(tree)
    scopes: list[ast.AST] = [tree, *(n for n in ast.walk(tree) if isinstance(n, _SCOPE))]
    for scope in scopes:
        local_names = module_names if scope is tree else _assignments(scope)
        for call, loader in _path_load_calls(scope, aliases):
            _one_path_edge(call, loader, g, rel, root, path, local_names, module_names)


def _path_argument(call: ast.Call, loader: str) -> ast.expr | None:
    """The path a loader call executes: positional, else by keyword."""
    index, keyword = _PATH_LOADERS[loader]
    if len(call.args) > index:
        return call.args[index]
    return next((kw.value for kw in call.keywords if kw.arg == keyword), None)


def _unwrap_str(expr: ast.expr) -> ast.expr:
    """`str(p)` / `os.fspath(p)` -> `p`: a conversion does not change the file named.

    The hook passes `str(FINDINGS)` to SourceFileLoader; read as a Call, the
    whole argument was an anchor with no segment and nothing resolved.
    """
    while (
        isinstance(expr, ast.Call)
        and len(expr.args) == 1
        and not expr.keywords
        and (getattr(expr.func, "id", None) or getattr(expr.func, "attr", None))
        in ("str", "fspath")
    ):
        expr = expr.args[0]
    return expr


def _one_path_edge(
    call: ast.Call,
    loader: str,
    g: Graph,
    rel: str,
    root: Path,
    path: Path,
    local_names: dict[str, ast.expr | None],
    module_names: dict[str, ast.expr | None],
) -> None:
    arg = _path_argument(call, loader)
    if arg is None:
        g.errors.append(f"{rel}: {loader} with no path argument")
        return

    def lookup(name: str) -> ast.expr | _Unbound | None:
        # Function scope shadows module scope, as Python does.
        return (local_names if name in local_names else module_names).get(name, _UNBOUND)

    expr = _unwrap_str(arg)
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
            expr = _unwrap_str(bound)
    segments = _literal_path_segments(expr, lookup)
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
        _import_edges(tree, g, rel, root, path)
        _dynamic_import_edges(tree, g, rel, root, path)
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
            # Unrankable is not compliant: skipping it passed the very edge
            # the rule cannot judge (audit-7d8bf871).
            out.append(f"  {e.src} -> {e.dst}: an endpoint is outside every ring")
            continue
        if rank[dst_ring] > rank[src_ring]:
            out.append(
                f"  {e.src} ({src_ring}) -> {e.dst} ({dst_ring}): "
                f"a {src_ring} module must not depend on {dst_ring}"
            )
    return out


def render(g: Graph) -> str:
    """The graph by ring, then a totals line counting each edge kind.

    Counts dynamic imports separately (audit-0dac429b), so an edge the import
    graph cannot see stays as visible as a string-path load.
    """
    lines: list[str] = []
    for ring, _ in RINGS:
        members = [e for e in g.edges if g.modules.get(e.src) == ring]
        lines.append(f"{ring}:")
        lines.extend(e.render() for e in members) if members else lines.append("  (no edges)")
    kinds = ("import", "dynamic", "path", "path-sibling")
    counts = {k: sum(1 for e in g.edges if e.kind == k) for k in kinds}
    lines.append("")
    lines.append(
        f"{len(g.modules)} modules, {len(g.edges)} edges "
        f"({counts['import']} import, {counts['dynamic']} dynamic import, "
        f"{counts['path']} string-path, "
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
