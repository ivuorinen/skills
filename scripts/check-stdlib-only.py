#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = "==3.11.*"
# ///
"""Enforce the shipped/internal script contract from `.claude/rules/use-uv-runner.md`.

Two checks:

1. Shipped skill tools (`skills/*/scripts/*.py`) import only the standard library.
2. The script-runner contract: shipped tools begin with `#!/usr/bin/env python3`
   and carry no `# /// script` block; internal tooling (`scripts/*.py`,
   `scripts/hooks/*.py`) that is a runnable script (has a shebang or a
   `# /// script` block) begins with `#!/usr/bin/env -S uv run --quiet`.
   Shebang-less library modules (e.g. `common.py`, `_hooklib.py`) are exempt.

uv is not available on consumer machines, so a third-party import — or an
internal-tooling shebang/metadata block — in a shipped tool breaks it under
plain `python3`, exactly the failure the rule forbids. Ruff cannot catch either
(it resolves neither imports nor shebangs), so this check gates the directory.

Limitations — three static-analysis blind spots:

* a dynamic import with a *computed* module name (not a string literal) cannot
  be resolved statically;
* an alias bound to the import function hides the call
  (``imp = importlib.import_module`` then ``imp("requests")``);
* a module name reaching the interpreter through ``exec``/``eval`` string
  arguments is never parsed as an import at all — so a call to either is
  flagged outright (see ``_uncheckable_calls``).

The stdlib allowlist is the running interpreter's ``sys.stdlib_module_names``.
The PEP 723 block above pins the interpreter to ``==3.11.*`` — the minimum
supported Python — so uv cannot select a newer one whose allowlist would
wrongly accept a module added to the stdlib after 3.11.
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


_IMPORT_ATTRS = {"import_module", "__import__"}


def _is_dynamic_import_func(func: ast.expr, aliases: set[str]) -> bool:
    """True if ``func`` is a dynamic-import callable: ``__import__``,
    ``x.import_module``/``x.__import__``, a name aliased to one of those
    (``imp = importlib.import_module``), or ``getattr(x, "import_module")``.
    """
    if isinstance(func, ast.Name):
        return func.id == "__import__" or func.id in aliases
    if isinstance(func, ast.Attribute):
        return func.attr in _IMPORT_ATTRS
    if isinstance(func, ast.Call):  # getattr(x, "import_module")(...)
        gf = func.func
        if isinstance(gf, ast.Name) and gf.id == "getattr" and len(func.args) >= 2:
            attr = func.args[1]
            return isinstance(attr, ast.Constant) and attr.value in _IMPORT_ATTRS
    return False


def _import_aliases(tree: ast.AST) -> set[str]:
    """Local names bound to ``importlib.import_module``/``__import__`` — an alias
    hides the module name from a naive direct-call check.
    """
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            v = node.value
            bound = (isinstance(v, ast.Attribute) and v.attr in _IMPORT_ATTRS) or (
                isinstance(v, ast.Name) and v.id == "__import__"
            )
            if bound:
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        aliases.add(t.id)
    return aliases


def _dynamic_import_root(call: ast.Call, aliases: set[str] | None = None) -> str | None:
    """Root module of a string-literal dynamic-import call.

    Only literal arguments are resolvable; a computed module name cannot be
    determined statically (documented limitation in the module docstring).
    ``aliases`` names locals bound to the import function; pass the set from
    ``_import_aliases`` to catch aliased/``getattr`` forms.
    """
    if _is_dynamic_import_func(call.func, aliases or set()) and call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value.split(".")[0]
    return None


def _module_roots(tree: ast.AST) -> set[str]:
    """Top-level module name of every import (relative imports skipped).

    Covers static ``import``/``from ... import`` and string-literal dynamic
    imports (``__import__("x")``, ``importlib.import_module("x")``, aliased and
    ``getattr``-wrapped forms).
    """
    roots: set[str] = set()
    aliases = _import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            root = _dynamic_import_root(node, aliases)
            if root:
                roots.add(root)
    return roots


def _uncheckable_calls(tree: ast.AST) -> list[str]:
    """Names of ``exec``/``eval`` calls — imports hidden in a string this check cannot read.

    A shipped tool has no legitimate use for either, so their presence is a
    violation rather than a limitation to document.
    """
    return sorted(
        {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"exec", "eval"}
        }
    )


SHIPPED_GLOB = "skills/*/scripts/**/*.py"

# A shipped tool's source, or the error that prevented reading it.
Collected = tuple[list[Path], dict[Path, "str | Exception"], dict[Path, set[str]]]


def _tree_root(repo_root: Path, script: Path) -> Path:
    """The `skills/<skill>/scripts` dir a shipped tool lives under."""
    return repo_root.joinpath(*script.relative_to(repo_root).parts[:3])


def collect(repo_root: Path) -> Collected:
    """Glob and read every shipped tool once: (scripts, sources, first-party names by tree).

    Hoisted out of the check functions so a run globs the tree once and reads
    each file once, instead of once per check — and so the sibling lookup is
    built per skill rather than per script.
    """
    scripts = sorted(repo_root.glob(SHIPPED_GLOB))
    sources: dict[Path, str | Exception] = {}
    siblings_by_tree: dict[Path, set[str]] = {}
    for script in scripts:
        try:
            sources[script] = script.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            sources[script] = e
        # The skill's whole scripts/ tree is first-party, so a nested module
        # importing a parent-dir sibling is not mistaken for an external package.
        tree_root = _tree_root(repo_root, script)
        if tree_root not in siblings_by_tree:
            names = {p.stem for p in tree_root.rglob("*.py")}
            siblings_by_tree[tree_root] = names | {n.replace("-", "_") for n in names}
    return scripts, sources, siblings_by_tree


def find_violations(repo_root: Path, collected: Collected | None = None) -> list[str]:
    """Return one message per non-stdlib import found in a shipped skill tool."""
    scripts, sources, siblings_by_tree = collected or collect(repo_root)
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    problems: list[str] = []
    for script in scripts:
        rel = script.relative_to(repo_root)
        text = sources[script]
        if isinstance(text, Exception):
            problems.append(f"  {rel}: cannot parse — {text}")
            continue
        try:
            tree = ast.parse(text, filename=str(script))
        except SyntaxError as e:
            problems.append(f"  {rel}: cannot parse — {e}")
            continue
        siblings = siblings_by_tree[_tree_root(repo_root, script)]
        for root in sorted(_module_roots(tree)):
            if root in stdlib or root in siblings:
                continue
            problems.append(
                f"  {rel}: non-stdlib import '{root}' "
                "— shipped tools run under plain python3 (see .claude/rules/use-uv-runner.md)"
            )
        for name in _uncheckable_calls(tree):
            problems.append(
                f"  {rel}: call to {name}() — a shipped tool must not run code from a "
                "string; it hides imports from this check"
            )
    return problems


SHIPPED_SHEBANG = "#!/usr/bin/env python3"
INTERNAL_SHEBANG = "#!/usr/bin/env -S uv run --quiet"


def _has_pep723(text: str) -> bool:
    """True if the file carries a PEP 723 `# /// script` inline-metadata block."""
    return any(line.strip() == "# /// script" for line in text.splitlines())


def find_runner_violations(repo_root: Path, collected: Collected | None = None) -> list[str]:
    """One message per shebang/metadata breach of the two-tier runner contract."""
    scripts, sources, _ = collected or collect(repo_root)
    problems: list[str] = []
    for script in scripts:
        rel = script.relative_to(repo_root)
        text = sources[script]
        if isinstance(text, Exception):
            problems.append(f"  {rel}: cannot read — {text}")
            continue
        lines = text.splitlines()
        first = lines[0] if lines else ""
        if first != SHIPPED_SHEBANG:
            problems.append(
                f"  {rel}: shipped tool must start with '{SHIPPED_SHEBANG}' (got {first!r})"
            )
        if _has_pep723(text):
            problems.append(
                f"  {rel}: shipped tool must carry no '# /// script' block "
                "(uv is not available on consumer machines)"
            )
    internal = [
        *sorted(repo_root.glob("scripts/*.py")),
        *sorted(repo_root.glob("scripts/hooks/*.py")),
    ]
    for script in internal:
        rel = script.relative_to(repo_root)
        try:
            text = script.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            problems.append(f"  {rel}: cannot read — {e}")
            continue
        lines = text.splitlines()
        first = lines[0] if lines else ""
        # A shebang-less, metadata-less file is an imported library — exempt.
        if (first.startswith("#!") or _has_pep723(text)) and first != INTERNAL_SHEBANG:
            problems.append(
                f"  {rel}: internal tool must start with '{INTERNAL_SHEBANG}' (got {first!r})"
            )
    return problems


def main() -> int:
    # Both checks always run: find_runner_violations also covers internal
    # tooling, which an early return on an empty shipped-tool glob would skip.
    collected = collect(REPO_ROOT)
    scripts = collected[0]
    import_problems = find_violations(REPO_ROOT, collected)
    runner_problems = find_runner_violations(REPO_ROOT, collected)
    if import_problems:
        print("Non-stdlib imports in shipped skill tools:")
        print("\n".join(import_problems))
    if runner_problems:
        print("Script-runner contract violations (see .claude/rules/use-uv-runner.md):")
        print("\n".join(runner_problems))
    total = len(import_problems) + len(runner_problems)
    if not scripts:
        # This repo ships skill tools; matching none means the glob is broken,
        # which would silently pass every shipped tool through unchecked.
        print(f"  ERROR  no shipped skill tool matched '{SHIPPED_GLOB}' — the glob is stale.")
        return 1
    if total:
        print(f"\n{total} violation(s).")
        return 1
    print(f"OK  {len(scripts)} shipped skill tool(s): stdlib-only, runner contract intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
