"""Tests for skills/cr-implementer/fetch-pr-comments.py."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TOOL = Path(__file__).parent.parent / "skills" / "cr-implementer" / "fetch-pr-comments.py"
_spec = importlib.util.spec_from_file_location("fetch_pr_comments", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_gh_available = _mod._gh_available
_gh_graphql = _mod._gh_graphql
_gh_rest_paginate = _mod._gh_rest_paginate
_token_rest_paginate = _mod._token_rest_paginate
_build_thread = _mod._build_thread
_build_comment = _mod._build_comment
_group_rest_comments = _mod._group_rest_comments
fetch_graphql = _mod.fetch_graphql
fetch_rest_gh = _mod.fetch_rest_gh
fetch_rest_token = _mod.fetch_rest_token


def _proc(stdout=b"", returncode=0, stderr=b"") -> MagicMock:
    p = MagicMock(spec=subprocess.CompletedProcess)
    p.stdout = stdout
    p.returncode = returncode
    p.stderr = stderr
    return p


def _http_resp(body, link: str = "") -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode()
    resp.headers.get.return_value = link
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── _gh_available ──────────────────────────────────────────────────────────────


class TestGhAvailable:
    def test_gh_found_returns_true(self):
        with patch("subprocess.run", return_value=_proc(returncode=0)):
            assert _gh_available() is True

    def test_gh_not_found_returns_false(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert _gh_available() is False

    def test_gh_nonzero_returns_false(self):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh")):
            assert _gh_available() is False

    def test_gh_timeout_returns_false(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 5)):
            assert _gh_available() is False


# ── _gh_graphql ────────────────────────────────────────────────────────────────


class TestGhGraphql:
    def test_success_returns_parsed_json(self):
        payload = {"data": {"repository": {}}}
        with patch("subprocess.run", return_value=_proc(stdout=json.dumps(payload).encode())):
            result = _gh_graphql("query {}", {})
        assert result == payload

    def test_nonzero_raises_runtime_error(self):
        with (
            patch("subprocess.run", return_value=_proc(returncode=1, stderr=b"auth error")),
            pytest.raises(RuntimeError, match="auth error"),
        ):
            _gh_graphql("query {}", {})


# ── _gh_rest_paginate ──────────────────────────────────────────────────────────


class TestGhRestPaginate:
    def test_success_returns_parsed_json(self):
        data = [{"id": 1}, {"id": 2}]
        with patch("subprocess.run", return_value=_proc(stdout=json.dumps(data).encode())):
            result = _gh_rest_paginate("repos/o/r/pulls/1/comments")
        assert result == data

    def test_nonzero_raises_runtime_error(self):
        with (
            patch("subprocess.run", return_value=_proc(returncode=1, stderr=b"not found")),
            pytest.raises(RuntimeError, match="not found"),
        ):
            _gh_rest_paginate("repos/o/r/pulls/1/comments")


# ── _token_rest_paginate ───────────────────────────────────────────────────────

_COMMENTS_URL = "https://api.github.com/repos/o/r/pulls/1/comments"
_NEXT_LINK = '<https://api.github.com/page2>; rel="next", <https://api.github.com/last>; rel="last"'


class TestTokenRestPaginate:
    def test_single_page_list(self):
        data = [{"id": 1}]
        with patch("urllib.request.urlopen", return_value=_http_resp(data)):
            result = _token_rest_paginate(_COMMENTS_URL, "token")
        assert result == data

    def test_non_list_response_wrapped(self):
        data = {"id": 1}
        with patch("urllib.request.urlopen", return_value=_http_resp(data)):
            result = _token_rest_paginate(_COMMENTS_URL, "token")
        assert result == [data]

    def test_multi_page_follows_link_header(self):
        page1 = [{"id": 1}]
        page2 = [{"id": 2}]
        calls = iter([_http_resp(page1, _NEXT_LINK), _http_resp(page2)])
        with patch("urllib.request.urlopen", side_effect=calls):
            result = _token_rest_paginate(_COMMENTS_URL, "token")
        assert result == [{"id": 1}, {"id": 2}]

    def test_no_link_header_stops_pagination(self):
        data = [{"id": 1}]
        with patch("urllib.request.urlopen", return_value=_http_resp(data, "")):
            result = _token_rest_paginate(_COMMENTS_URL, "token")
        assert len(result) == 1


# ── _build_thread / _build_comment ────────────────────────────────────────────


class TestBuildHelpers:
    def test_build_thread_fields(self):
        comment = {"id": 42, "path": "src/foo.py", "diff_hunk": "@@ @@", "body": "x"}
        thread = _build_thread(comment)
        assert thread["thread_id"] == "42"
        assert thread["path"] == "src/foo.py"
        assert thread["diff_hunk"] == "@@ @@"
        assert thread["is_resolved"] is None
        assert thread["comments"] == []

    def test_build_thread_missing_optional_fields(self):
        comment = {"id": 1}
        thread = _build_thread(comment)
        assert thread["path"] == ""
        assert thread["diff_hunk"] == ""

    def test_build_comment_fields(self):
        comment = {
            "id": 99,
            "user": {"login": "alice"},
            "body": "Fix this.",
            "created_at": "2026-01-01T00:00:00Z",
            "diff_hunk": "@@ @@",
        }
        c = _build_comment(comment)
        assert c["id"] == "99"
        assert c["author"] == "alice"
        assert c["body"] == "Fix this."
        assert c["diff_hunk"] == "@@ @@"

    def test_build_comment_missing_user(self):
        comment = {"id": 1, "body": "x", "created_at": "", "diff_hunk": ""}
        c = _build_comment(comment)
        assert c["author"] == "unknown"

    def test_build_comment_null_user(self):
        comment = {"id": 1, "user": None, "body": "x", "created_at": "", "diff_hunk": ""}
        c = _build_comment(comment)
        assert c["author"] == "unknown"


# ── _group_rest_comments ───────────────────────────────────────────────────────


class TestGroupRestComments:
    def test_empty_list(self):
        assert _group_rest_comments([]) == []

    def test_single_root_comment(self):
        raw = [
            {
                "id": 1,
                "path": "f.py",
                "diff_hunk": "@@ @@",
                "body": "x",
                "user": {"login": "a"},
                "created_at": "t",
            }
        ]
        threads = _group_rest_comments(raw)
        assert len(threads) == 1
        assert len(threads[0]["comments"]) == 1

    def test_reply_grouped_with_parent(self):
        raw = [
            {
                "id": 1,
                "path": "f.py",
                "diff_hunk": "@@ @@",
                "body": "root",
                "user": {"login": "a"},
                "created_at": "t",
            },
            {
                "id": 2,
                "in_reply_to_id": 1,
                "path": "f.py",
                "diff_hunk": "@@ @@",
                "body": "reply",
                "user": {"login": "b"},
                "created_at": "t",
            },
        ]
        threads = _group_rest_comments(raw)
        assert len(threads) == 1
        assert len(threads[0]["comments"]) == 2

    def test_multiple_threads(self):
        raw = [
            {
                "id": 1,
                "path": "a.py",
                "diff_hunk": "@@ @@",
                "body": "c1",
                "user": {"login": "a"},
                "created_at": "t",
            },
            {
                "id": 3,
                "path": "b.py",
                "diff_hunk": "@@ @@",
                "body": "c3",
                "user": {"login": "b"},
                "created_at": "t",
            },
        ]
        threads = _group_rest_comments(raw)
        assert len(threads) == 2


# ── fetch_graphql ──────────────────────────────────────────────────────────────


class TestFetchGraphql:
    def _graphql_response(self, nodes: list, has_next: bool = False, cursor: str = "") -> dict:
        return {
            "data": {
                "repository": {
                    "pullRequest": {
                        "reviewThreads": {
                            "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                            "nodes": nodes,
                        }
                    }
                }
            }
        }

    def _thread_node(self, resolved: bool = False, comments: list | None = None) -> dict:
        default_comments = [
            {
                "id": "C_1",
                "body": "Please fix this.",
                "createdAt": "2026-01-01",
                "author": {"login": "reviewer"},
                "diffHunk": "@@ @@",
            }
        ]
        return {
            "id": "T_1",
            "isResolved": resolved,
            "path": "src/foo.py",
            "comments": {"nodes": comments if comments is not None else default_comments},
        }

    def test_unresolved_thread_returned(self):
        resp = self._graphql_response([self._thread_node(resolved=False)])
        with patch.object(_mod, "_gh_graphql", return_value=resp):
            threads = fetch_graphql("owner", "repo", 1)
        assert len(threads) == 1
        assert threads[0]["is_resolved"] is False

    def test_resolved_thread_excluded(self):
        resp = self._graphql_response([self._thread_node(resolved=True)])
        with patch.object(_mod, "_gh_graphql", return_value=resp):
            threads = fetch_graphql("owner", "repo", 1)
        assert threads == []

    def test_pagination(self):
        node = self._thread_node()
        resp1 = self._graphql_response([node], has_next=True, cursor="cursor1")
        resp2 = self._graphql_response([node], has_next=False)
        with patch.object(_mod, "_gh_graphql", side_effect=[resp1, resp2]):
            threads = fetch_graphql("owner", "repo", 1)
        assert len(threads) == 2

    def test_errors_key_raises(self):
        resp = {"errors": [{"message": "Not found"}]}
        with (
            patch.object(_mod, "_gh_graphql", return_value=resp),
            pytest.raises(RuntimeError),
        ):
            fetch_graphql("owner", "repo", 1)

    def test_empty_comments_node(self):
        node = self._thread_node(comments=[])
        resp = self._graphql_response([node])
        with patch.object(_mod, "_gh_graphql", return_value=resp):
            threads = fetch_graphql("owner", "repo", 1)
        assert threads[0]["diff_hunk"] == ""

    def test_thread_path_and_comments(self):
        node = self._thread_node()
        resp = self._graphql_response([node])
        with patch.object(_mod, "_gh_graphql", return_value=resp):
            threads = fetch_graphql("owner", "repo", 1)
        assert threads[0]["path"] == "src/foo.py"
        assert threads[0]["comments"][0]["author"] == "reviewer"

    def test_null_author_handled(self):
        node = {
            "id": "T_1",
            "isResolved": False,
            "path": "f.py",
            "comments": {
                "nodes": [
                    {
                        "id": "C_1",
                        "body": "x",
                        "createdAt": "2026-01-01",
                        "author": None,
                        "diffHunk": "@@ @@",
                    }
                ]
            },
        }
        resp = self._graphql_response([node])
        with patch.object(_mod, "_gh_graphql", return_value=resp):
            threads = fetch_graphql("owner", "repo", 1)
        assert threads[0]["comments"][0]["author"] == "unknown"


# ── fetch_rest_gh / fetch_rest_token ──────────────────────────────────────────


class TestFetchRestGh:
    def test_calls_rest_paginate(self):
        raw = [
            {
                "id": 1,
                "path": "f.py",
                "diff_hunk": "@@ @@",
                "body": "x",
                "user": {"login": "a"},
                "created_at": "t",
            }
        ]
        with patch.object(_mod, "_gh_rest_paginate", return_value=raw):
            threads = fetch_rest_gh("owner", "repo", 1)
        assert len(threads) == 1


class TestFetchRestToken:
    def test_calls_token_paginate(self):
        raw = [
            {
                "id": 1,
                "path": "f.py",
                "diff_hunk": "@@ @@",
                "body": "x",
                "user": {"login": "a"},
                "created_at": "t",
            }
        ]
        with patch.object(_mod, "_token_rest_paginate", return_value=raw):
            threads = fetch_rest_token("owner", "repo", 1, "tok")
        assert len(threads) == 1


# ── main ──────────────────────────────────────────────────────────────────────


class TestMain:
    _THREADS = [
        {
            "thread_id": "T_1",
            "path": "f.py",
            "is_resolved": False,
            "diff_hunk": "@@ @@",
            "comments": [],
        }
    ]

    def test_owner_repo_pr_format(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner", "repo", "42"])
        with (
            patch.object(_mod, "_gh_available", return_value=True),
            patch.object(_mod, "fetch_graphql", return_value=self._THREADS),
        ):
            _mod.main()
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1

    def test_owner_slash_repo_format(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "42"])
        with (
            patch.object(_mod, "_gh_available", return_value=True),
            patch.object(_mod, "fetch_graphql", return_value=self._THREADS),
        ):
            _mod.main()
        assert json.loads(capsys.readouterr().out)

    def test_no_args_exits_2(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog"])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 2

    def test_non_integer_pr_exits_2(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "not-a-number"])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 2

    def test_wrong_arg_count_exits_2(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "a", "b", "c", "d"])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 2

    def test_gh_graphql_fails_falls_back_to_rest(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "1"])
        with (
            patch.object(_mod, "_gh_available", return_value=True),
            patch.object(_mod, "fetch_graphql", side_effect=RuntimeError("gql error")),
            patch.object(_mod, "fetch_rest_gh", return_value=self._THREADS),
        ):
            _mod.main()
        assert json.loads(capsys.readouterr().out)

    def test_gh_rest_fails_no_token_exits_1(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "1"])
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with (
            patch.object(_mod, "_gh_available", return_value=True),
            patch.object(_mod, "fetch_graphql", side_effect=RuntimeError("gql")),
            patch.object(_mod, "fetch_rest_gh", side_effect=RuntimeError("rest")),
            pytest.raises(SystemExit) as exc,
        ):
            _mod.main()
        assert exc.value.code == 1

    def test_gh_rest_fails_falls_back_to_token(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "1"])
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        with (
            patch.object(_mod, "_gh_available", return_value=True),
            patch.object(_mod, "fetch_graphql", side_effect=RuntimeError("gql")),
            patch.object(_mod, "fetch_rest_gh", side_effect=RuntimeError("rest")),
            patch.object(_mod, "fetch_rest_token", return_value=self._THREADS),
        ):
            _mod.main()
        assert json.loads(capsys.readouterr().out)

    def test_gh_rest_fails_token_rest_also_fails_exits_1(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "1"])
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        with (
            patch.object(_mod, "_gh_available", return_value=True),
            patch.object(_mod, "fetch_graphql", side_effect=RuntimeError("gql")),
            patch.object(_mod, "fetch_rest_gh", side_effect=RuntimeError("rest")),
            patch.object(_mod, "fetch_rest_token", side_effect=RuntimeError("token fail")),
            pytest.raises(SystemExit) as exc,
        ):
            _mod.main()
        assert exc.value.code == 1

    def test_no_gh_with_token_uses_rest(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "1"])
        monkeypatch.setenv("GITHUB_TOKEN", "my-token")
        with (
            patch.object(_mod, "_gh_available", return_value=False),
            patch.object(_mod, "fetch_rest_token", return_value=self._THREADS),
        ):
            _mod.main()
        assert json.loads(capsys.readouterr().out)

    def test_no_gh_no_token_exits_1(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "1"])
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with (
            patch.object(_mod, "_gh_available", return_value=False),
            pytest.raises(SystemExit) as exc,
        ):
            _mod.main()
        assert exc.value.code == 1

    def test_no_gh_token_rest_fails_exits_1(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "1"])
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        with (
            patch.object(_mod, "_gh_available", return_value=False),
            patch.object(_mod, "fetch_rest_token", side_effect=Exception("fail")),
            pytest.raises(SystemExit) as exc,
        ):
            _mod.main()
        assert exc.value.code == 1
