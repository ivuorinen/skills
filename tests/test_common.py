"""Tests for scripts/common.py — parse_frontmatter."""

import ast
import importlib.util
import inspect
import textwrap
from pathlib import Path

from common import parse_frontmatter  # type: ignore[import-not-found]


def _fm(text: str) -> dict:
    fm, _ = parse_frontmatter(text)
    return fm


def _body(text: str) -> str:
    _, body = parse_frontmatter(text)
    return body


def _body_ast(func) -> str:
    """Normalized AST of a function's statements, minus its docstring.

    Comparing the dumped AST (not the text) ignores the docstring, comments and
    formatting, so only a real behavioural difference fails the comparison.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    body = tree.body[0].body  # type: ignore[attr-defined]
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return "\n".join(ast.dump(stmt) for stmt in body)


class TestParseFrontmatter:
    def test_valid_returns_dict_and_body(self):
        text = "---\nname: my-skill\ndescription: Use when testing\n---\n\n# Body\n"
        fm, body = parse_frontmatter(text)
        assert fm == {"name": "my-skill", "description": "Use when testing"}
        assert body == "\n# Body\n"

    def test_no_frontmatter_returns_empty_dict(self):
        text = "# Just a body\nno frontmatter here\n"
        fm, body = parse_frontmatter(text)
        assert fm == {}
        assert body == text

    def test_missing_closing_marker_returns_empty_dict(self):
        text = "---\nname: my-skill\n"
        fm, body = parse_frontmatter(text)
        assert fm == {}
        assert body == text

    def test_single_quoted_value_stripped(self):
        text = "---\nname: 'my-skill'\n---\nbody\n"
        assert _fm(text)["name"] == "my-skill"

    def test_double_quoted_value_stripped(self):
        text = '---\nname: "my-skill"\n---\nbody\n'
        assert _fm(text)["name"] == "my-skill"

    def test_multi_colon_value_preserves_full_value(self):
        text = "---\ndescription: Use when a: b: c\n---\nbody\n"
        assert _fm(text)["description"] == "Use when a: b: c"

    def test_whitespace_stripped_from_value(self):
        text = "---\nname:   spaced   \n---\nbody\n"
        assert _fm(text)["name"] == "spaced"

    def test_unknown_fields_preserved(self):
        text = "---\nname: foo\ndisable-model-invocation: true\n---\nbody\n"
        fm = _fm(text)
        assert fm["disable-model-invocation"] == "true"

    def test_body_starts_after_closing_marker(self):
        text = "---\nname: foo\n---\n## Section\n"
        assert _body(text) == "## Section\n"

    def test_common_reexports_the_shipped_parser(self):
        # common.parse_frontmatter is no longer a clone: it IS the shipped
        # implementation, path-loaded. Drift is therefore impossible by
        # construction — this pins the re-export so a future edit cannot
        # reintroduce a second copy without failing here.
        spec = importlib.util.spec_from_file_location(
            "findings_for_identity_check",
            Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "findings.py",
        )
        findings = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(findings)  # type: ignore[union-attr]
        assert _body_ast(parse_frontmatter) == _body_ast(findings.parse_frontmatter)
        assert parse_frontmatter.__module__ != "common"

    def test_indented_key_is_not_parsed_as_frontmatter_field(self):
        # An indented key is a nested-mapping value in YAML, not a top-level
        # field. Both parsers must agree: otherwise an accidentally-indented
        # `name:` passes validate-skill.py with a parsed name while the same
        # indentation is dropped in a .claude/rules/ file.
        assert _fm("---\n  indented: v\n---\nb") == {}

    def test_empty_frontmatter_returns_empty_dict(self):
        # parse_frontmatter searches for "\n---\n" from position 4, so the closing
        # marker must appear on its own line after at least one character/blank.
        text = "---\n\n---\nbody\n"
        assert _fm(text) == {}
        assert _body(text) == "body\n"
