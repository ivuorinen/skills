"""Tests for scripts/common.py — parse_frontmatter."""

from common import parse_frontmatter  # type: ignore[import-not-found]  # noqa: E402


def _fm(text: str) -> dict:
    fm, _ = parse_frontmatter(text)
    return fm


def _body(text: str) -> str:
    _, body = parse_frontmatter(text)
    return body


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

    def test_empty_frontmatter_returns_empty_dict(self):
        # parse_frontmatter searches for "\n---\n" from position 4, so the closing
        # marker must appear on its own line after at least one character/blank.
        text = "---\n\n---\nbody\n"
        assert _fm(text) == {}
        assert _body(text) == "body\n"
