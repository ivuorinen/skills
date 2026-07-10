#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
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

Limitations: a dynamic import with a *computed* module name (not a string
literal) cannot be resolved statically. The stdlib allowlist is the running
interpreter's ``sys.stdlib_module_names``; run this under the minimum supported
Python (3.11) so a module added to the stdlib in a later version is not
wrongly accepted for a 3.11 consumer.
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def _dynamic_import_root(call: ast.Call) -> str | None:
    """Root module of a string-literal ``__import__``/``importlib.import_module`` call.

    Only literal arguments are resolvable; a computed module name cannot be
    determined statically (documented limitation in the module docstring).
    """
    func = call.func
    is_dynamic = (isinstance(func, ast.Name) and func.id == "__import__") or (
        isinstance(func, ast.Attribute) and func.attr in {"import_module", "__import__"}
    )
    if is_dynamic and call.args:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value.split(".")[0]
    return None


def _module_roots(tree: ast.AST) -> set[str]:
    """Top-level module name of every import (relative imports skipped).

    Covers static ``import``/``from ... import`` and string-literal dynamic
    imports (``__import__("x")``, ``importlib.import_module("x")``).
    """
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            roots.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            root = _dynamic_import_root(node)
            if root:
                roots.add(root)
    return roots


def find_violations(repo_root: Path) -> list[str]:
    """Return one message per non-stdlib import found in a shipped skill tool."""
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    problems: list[str] = []
    for script in sorted(repo_root.glob("skills/*/scripts/*.py")):
        # A sibling .py in the same scripts/ dir is first-party, not external.
        siblings = {p.stem for p in script.parent.glob("*.py")}
        siblings |= {s.replace("-", "_") for s in siblings}
        try:
            tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
        except (OSError, SyntaxError, UnicodeDecodeError) as e:
            problems.append(f"  {script.relative_to(repo_root)}: cannot parse — {e}")
            continue
        for root in sorted(_module_roots(tree)):
            if root in stdlib or root in siblings:
                continue
            problems.append(
                f"  {script.relative_to(repo_root)}: non-stdlib import '{root}' "
                "— shipped tools run under plain python3 (see .claude/rules/use-uv-runner.md)"
            )
    return problems


SHIPPED_SHEBANG = "#!/usr/bin/env python3"
INTERNAL_SHEBANG = "#!/usr/bin/env -S uv run --quiet"


def _has_pep723(text: str) -> bool:
    """True if the file carries a PEP 723 `# /// script` inline-metadata block."""
    return any(line.strip() == "# /// script" for line in text.splitlines())


def find_runner_violations(repo_root: Path) -> list[str]:
    """One message per shebang/metadata breach of the two-tier runner contract."""
    problems: list[str] = []
    for script in sorted(repo_root.glob("skills/*/scripts/*.py")):
        rel = script.relative_to(repo_root)
        try:
            text = script.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            problems.append(f"  {rel}: cannot read — {e}")
            continue
        first = text.splitlines()[0] if text.splitlines() else ""
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
        first = text.splitlines()[0] if text.splitlines() else ""
        # A shebang-less, metadata-less file is an imported library — exempt.
        if (first.startswith("#!") or _has_pep723(text)) and first != INTERNAL_SHEBANG:
            problems.append(
                f"  {rel}: internal tool must start with '{INTERNAL_SHEBANG}' (got {first!r})"
            )
    return problems


def main() -> int:
    scripts = sorted(REPO_ROOT.glob("skills/*/scripts/*.py"))
    if not scripts:
        print("OK  no shipped skill tools found.")
        return 0
    import_problems = find_violations(REPO_ROOT)
    runner_problems = find_runner_violations(REPO_ROOT)
    if import_problems or runner_problems:
        if import_problems:
            print("Non-stdlib imports in shipped skill tools:")
            print("\n".join(import_problems))
        if runner_problems:
            print("Script-runner contract violations (see .claude/rules/use-uv-runner.md):")
            print("\n".join(runner_problems))
        total = len(import_problems) + len(runner_problems)
        print(f"\n{total} violation(s).")
        return 1
    print(f"OK  {len(scripts)} shipped skill tool(s): stdlib-only, runner contract intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
