"""Tests for skills/nitpicker/scripts/fetch-pr-comments.py."""

import email.message
import importlib.util
import json
import runpy
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

_TOOL = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "fetch-pr-comments.py"
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
_token_transport = _mod._token_transport
_fetch_out_of_thread_notes = _mod._fetch_out_of_thread_notes


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
    def test_success_single_page_flattened(self):
        # --slurp wraps each page in outer array: [[item1, item2]]
        page = [{"id": 1}, {"id": 2}]
        slurp_output = json.dumps([page]).encode()
        with patch("subprocess.run", return_value=_proc(stdout=slurp_output)):
            result = _gh_rest_paginate("repos/o/r/pulls/1/comments")
        assert result == page

    def test_success_multi_page_flattened(self):
        # Two pages: [[item1], [item2, item3]] → [item1, item2, item3]
        page1 = [{"id": 1}]
        page2 = [{"id": 2}, {"id": 3}]
        slurp_output = json.dumps([page1, page2]).encode()
        with patch("subprocess.run", return_value=_proc(stdout=slurp_output)):
            result = _gh_rest_paginate("repos/o/r/pulls/1/comments")
        assert result == [{"id": 1}, {"id": 2}, {"id": 3}]

    def test_uses_slurp_flag(self):
        page = [{"id": 1}]
        slurp_out = json.dumps([page]).encode()
        with patch("subprocess.run", return_value=_proc(stdout=slurp_out)) as mock_run:
            _gh_rest_paginate("repos/o/r/pulls/1/comments")
        cmd = mock_run.call_args[0][0]
        assert "--slurp" in cmd

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

    def test_offhost_next_url_not_followed(self):
        # A malicious Link header pointing off-host must not receive the token.
        evil_link = '<https://evil.example.com/page2>; rel="next"'
        page1 = [{"id": 1}]
        resp = _http_resp(page1, evil_link)
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            result = _token_rest_paginate(_COMMENTS_URL, "token")
        assert result == page1
        assert mock_open.call_count == 1


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
            pytest.raises(RuntimeError, match="Not found"),
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

    def test_inner_comment_pagination_fetches_all_pages(self):
        # A thread whose first comment page reports hasNextPage must follow the
        # inner cursor and include the remaining comments, not truncate at 100.
        node = self._thread_node()  # first page: comment C_1
        node["comments"]["pageInfo"] = {"hasNextPage": True, "endCursor": "cc1"}
        resp = self._graphql_response([node])
        inner = {
            "data": {
                "node": {
                    "comments": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "C_2",
                                "body": "second page",
                                "createdAt": "2026-01-02",
                                "author": {"login": "reviewer2"},
                                "diffHunk": "@@ @@",
                            }
                        ],
                    }
                }
            }
        }
        with patch.object(_mod, "_gh_graphql", side_effect=[resp, inner]):
            threads = fetch_graphql("owner", "repo", 1)
        assert len(threads) == 1
        assert [c["id"] for c in threads[0]["comments"]] == ["C_1", "C_2"]

    def test_thread_deleted_mid_inner_pagination_does_not_crash(self):
        # A thread deleted/hidden between pages returns data.node == null; keep
        # the comments already fetched instead of crashing on None["comments"].
        node = self._thread_node()  # first page: comment C_1
        node["comments"]["pageInfo"] = {"hasNextPage": True, "endCursor": "cc1"}
        resp = self._graphql_response([node])
        gone = {"data": {"node": None}}
        with patch.object(_mod, "_gh_graphql", side_effect=[resp, gone]):
            threads = fetch_graphql("owner", "repo", 1)
        assert len(threads) == 1
        assert [c["id"] for c in threads[0]["comments"]] == ["C_1"]

    def test_null_pull_request_raises_not_found(self):
        resp = {"data": {"repository": {"pullRequest": None}}}
        with (
            patch.object(_mod, "_gh_graphql", return_value=resp),
            pytest.raises(RuntimeError, match="PR #1 not found in owner/repo"),
        ):
            fetch_graphql("owner", "repo", 1)

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
    _THREADS: ClassVar[list[dict]] = [
        {
            "thread_id": "T_1",
            "path": "f.py",
            "is_resolved": False,
            "diff_hunk": "@@ @@",
            "comments": [],
        }
    ]

    @pytest.fixture(autouse=True)
    def _stub_notes(self):
        # main() also fetches out-of-thread notes; stub it so these tests never hit
        # the network. Tests exercising the real fetch live in TestOutOfThreadNotes.
        with patch.object(_mod, "_fetch_out_of_thread_notes", return_value=([], [])):
            yield

    def test_owner_repo_pr_format(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "owner", "repo", "42"])
        with (
            patch.object(_mod, "_gh_available", return_value=True),
            patch.object(_mod, "fetch_graphql", return_value=self._THREADS),
        ):
            _mod.main()
        data = json.loads(capsys.readouterr().out)
        assert list(data.keys()) == ["threads", "review_bodies", "summary_comments"]
        assert len(data["threads"]) == 1
        assert data["review_bodies"] == [] and data["summary_comments"] == []

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

    @pytest.mark.parametrize(
        "owner, repo",
        [
            ("ow/ner", "repo"),
            ("owner", "re/po"),
            ("../etc", "repo"),
            ("owner", "../etc"),
            ("..", "repo"),
            ("owner", ".."),
            (".", "repo"),
            ("owner", "."),
            ("owner?x", "repo"),
            ("owner", "repo?x"),
            ("own er", "repo"),
        ],
    )
    def test_malicious_owner_repo_exits_2(self, owner, repo, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", owner, repo, "1"])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 2

    def test_valid_owner_repo_passes_validation(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", "valid.owner-1", "valid_repo.2", "42"])
        with (
            patch.object(_mod, "_gh_available", return_value=True),
            patch.object(_mod, "fetch_graphql", return_value=self._THREADS),
        ):
            _mod.main()
        assert json.loads(capsys.readouterr().out)

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


# ── _token_transport ───────────────────────────────────────────────────────────


class TestTokenTransport:
    def test_returns_callable_hitting_api_github(self):
        fn = _token_transport("tok")
        with patch.object(_mod, "_token_rest_paginate", return_value=[{"x": 1}]) as m:
            out = fn("repos/o/r/pulls/1/reviews")
        assert out == [{"x": 1}]
        assert m.call_args[0][0] == "https://api.github.com/repos/o/r/pulls/1/reviews"
        assert m.call_args[0][1] == "tok"


# ── main() carries the thread transport into the notes fetch ───────────────────


def _capture_notes_transport(monkeypatch, **thread_patches):
    """Run main() with the given thread-fetch patches and return the rest_list
    callable main() handed to _fetch_out_of_thread_notes."""
    captured = {}

    def _capture(_o, _r, _p, rest_list):
        captured["rest_list"] = rest_list
        return ([], [])

    monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "1"])
    with patch.object(_mod, "_fetch_out_of_thread_notes", side_effect=_capture):
        for name, patched in thread_patches.items():
            monkeypatch.setattr(_mod, name, patched)
        _mod.main()
    return captured["rest_list"]


def test_notes_use_gh_transport_when_graphql_succeeds(monkeypatch):
    rest_list = _capture_notes_transport(
        monkeypatch,
        _gh_available=lambda: True,
        fetch_graphql=lambda *a: [],
    )
    assert rest_list is _mod._gh_rest_paginate


def test_notes_use_token_transport_when_threads_fell_back_to_token(monkeypatch):
    # gh GraphQL and gh REST both fail, token REST succeeds → the notes fetch must
    # NOT re-select the broken gh paginator (the bug CodeRabbit/Copilot flagged).
    monkeypatch.setenv("GITHUB_TOKEN", "tok")

    def _raise(*a):
        raise RuntimeError("gh path down")

    rest_list = _capture_notes_transport(
        monkeypatch,
        _gh_available=lambda: True,
        fetch_graphql=_raise,
        fetch_rest_gh=_raise,
        fetch_rest_token=lambda *a: [],
    )
    assert rest_list is not _mod._gh_rest_paginate
    assert callable(rest_list)


# ── _fetch_out_of_thread_notes ─────────────────────────────────────────────────


class TestOutOfThreadNotes:
    @staticmethod
    def _rest_list(reviews, comments):
        def _fake(path):
            if path.endswith("/reviews"):
                return reviews
            if path.endswith("/comments"):
                return comments
            return []

        return _fake

    def test_review_bodies_keep_nonempty_any_author(self):
        reviews = [
            {
                "user": {"login": "human"},
                "state": "COMMENTED",
                "commit_id": "abcdef1234567890",
                "submitted_at": "t",
                "body": "Outside diff range note",
            },
            {"user": {"login": "x[bot]"}, "state": "COMMENTED", "body": "   "},  # empty → dropped
        ]
        rb, _ = _fetch_out_of_thread_notes("o", "r", 1, self._rest_list(reviews, []))
        assert len(rb) == 1
        assert rb[0]["author"] == "human"  # any author, not just bots
        assert rb[0]["commit_id"] == "abcdef123456"  # truncated to 12
        assert rb[0]["body"] == "Outside diff range note"

    def test_summary_comments_keep_nonempty_any_author(self):
        # Any author, like review bodies above. A bot-only filter dropped a
        # maintainer's plain PR comment entirely, so `cr` could neither act on it
        # nor record a verdict — the silent miss this fetch exists to prevent.
        comments = [
            {
                "user": {"login": "coderabbitai[bot]"},
                "created_at": "t0",
                "updated_at": "t1",
                "body": "Review limit reached",
            },
            {"user": {"login": "human"}, "created_at": "t", "body": "chatter"},
            {"user": {"login": "copilot[bot]"}, "created_at": "t", "body": "  "},  # empty → dropped
        ]
        _, sc = _fetch_out_of_thread_notes("o", "r", 1, self._rest_list([], comments))
        assert [c["author"] for c in sc] == ["coderabbitai[bot]", "human"]
        assert sc[0]["body"] == "Review limit reached"
        assert sc[0]["updated_at"] == "t1"  # loop measures rate-limit wait from last edit
        assert sc[1]["body"] == "chatter"  # human note survives; author distinguishes it

    def test_null_user_does_not_crash(self):
        reviews = [{"user": None, "body": "note"}]
        comments = [{"user": None, "body": "x"}]
        rb, sc = _fetch_out_of_thread_notes("o", "r", 1, self._rest_list(reviews, comments))
        assert rb[0]["author"] == "unknown"
        assert [c["author"] for c in sc] == ["unknown"]  # unattributable, still actionable

    def test_partial_failure_keeps_the_other_half(self, capsys):
        # A failure fetching one section must not discard the other — review bodies
        # (outside-diff-range comments) must survive a summary-comment fetch failure.
        reviews = [
            {
                "user": {"login": "coderabbitai[bot]"},
                "state": "COMMENTED",
                "body": "outside-diff note",
            }
        ]

        def _rest(path):
            if path.endswith("/reviews"):
                return reviews
            raise RuntimeError("comments endpoint rate-limited")

        rb, sc = _fetch_out_of_thread_notes("o", "r", 1, _rest)
        assert len(rb) == 1  # survived the comments-endpoint failure
        assert sc == []
        assert "could not fetch summary comments" in capsys.readouterr().err


def test_main_notes_failure_still_returns_threads(capsys, monkeypatch):
    # Out-of-thread fetch is best-effort: if it raises, main still returns the
    # inline threads with the two note lists empty, and warns on stderr.
    monkeypatch.setattr(sys, "argv", ["prog", "owner/repo", "1"])
    threads = [
        {"thread_id": "T", "path": "f", "is_resolved": False, "diff_hunk": "", "comments": []}
    ]
    with (
        patch.object(_mod, "_gh_available", return_value=True),
        patch.object(_mod, "fetch_graphql", return_value=threads),
        patch.object(_mod, "_fetch_out_of_thread_notes", side_effect=RuntimeError("boom")),
    ):
        _mod.main()
    out = capsys.readouterr()
    data = json.loads(out.out)
    assert len(data["threads"]) == 1
    assert data["review_bodies"] == [] and data["summary_comments"] == []
    assert "could not fetch out-of-thread notes" in out.err


def test_main_hard_fails_on_graphql_shape_bug_without_rest_downgrade(monkeypatch):
    """A GraphQL response-shape bug (TypeError, e.g. `repository: null`) must NOT be
    caught and downgraded to resolved-blind REST — it propagates as a hard error."""
    monkeypatch.setattr(sys, "argv", ["fetch-pr-comments.py", "owner", "repo", "1"])
    monkeypatch.setattr(_mod, "_gh_available", lambda: True)

    def _shape_bug(*a):
        raise TypeError("'NoneType' object is not subscriptable")

    monkeypatch.setattr(_mod, "fetch_graphql", _shape_bug)
    called = {"rest": False}

    def _rest(*a):
        called["rest"] = True
        return []

    monkeypatch.setattr(_mod, "fetch_rest_gh", _rest)
    # match=: it must be *this* shape bug propagating, not any TypeError raised
    # somewhere else on the way (which would also leave `rest` uncalled).
    with pytest.raises(TypeError, match="NoneType"):
        _mod.main()
    assert called["rest"] is False  # did not silently fall back to resolved-blind REST


# ── _TokenSafeRedirectHandler: the off-host token strip (tests-cb05831d) ───────
#
# urllib follows 3xx transparently and keeps Authorization across hosts. This
# handler is the only thing stopping $GITHUB_TOKEN from reaching a redirect
# target that is not api.github.com.


def _redirect(newurl: str, header: str = "Authorization") -> urllib.request.Request:
    req = urllib.request.Request(
        "https://api.github.com/repos/o/r/pulls/1/comments",
        headers={header: "token ghp_secret"},
    )
    handler = _mod._TokenSafeRedirectHandler()
    return handler.redirect_request(req, None, 302, "Found", email.message.Message(), newurl)


def _auth_headers(req: urllib.request.Request) -> list[str]:
    return [k for k in {**req.headers, **req.unredirected_hdrs} if k.lower() == "authorization"]


def test_redirect_off_host_strips_authorization():
    new = _redirect("https://evil.example/steal")
    assert new is not None
    assert _auth_headers(new) == []
    assert "ghp_secret" not in str({**new.headers, **new.unredirected_hdrs})


def test_redirect_same_host_keeps_authorization():
    new = _redirect("https://api.github.com/repositories/1/pulls/1/comments?page=2")
    assert _auth_headers(new) == ["Authorization"]


def test_redirect_off_host_strip_is_case_insensitive():
    # Request.add_header capitalizes keys, so the stored spelling is not the
    # caller's — the strip must match on lower(), not on an exact key.
    new = _redirect("http://127.0.0.1:8080/x", header="AUTHORIZATION")
    assert _auth_headers(new) == []


def test_redirect_passes_through_when_super_declines(monkeypatch):
    """The `new is not None` guard: a base handler that declines must not crash."""
    monkeypatch.setattr(
        urllib.request.HTTPRedirectHandler,
        "redirect_request",
        lambda *a, **k: None,
    )
    assert _redirect("https://evil.example/steal") is None


# ── remaining error paths (tests-b4fcf9ec) ────────────────────────────────────


def test_all_thread_comments_raises_on_errors_in_a_later_page():
    node = {
        "id": "T1",
        "comments": {
            "nodes": [{"id": "C1", "body": "a", "createdAt": "2026-07-08T00:00:00Z"}],
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
        },
    }
    with (
        patch.object(_mod, "_gh_graphql", return_value={"errors": [{"message": "boom"}]}),
        pytest.raises(RuntimeError, match="boom"),
    ):
        _mod._all_thread_comments(node)


def test_all_thread_comments_stops_when_thread_vanishes_mid_pagination():
    node = {
        "id": "T1",
        "comments": {
            "nodes": [{"id": "C1", "body": "a", "createdAt": "2026-07-08T00:00:00Z"}],
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
        },
    }
    with patch.object(_mod, "_gh_graphql", return_value={"data": {"node": None}}):
        assert len(_mod._all_thread_comments(node)) == 1


def test_out_of_thread_notes_warns_but_survives_review_body_failure(capsys):
    with (
        patch.object(_mod, "_fetch_review_bodies", side_effect=RuntimeError("rate limited")),
        patch.object(_mod, "_fetch_summary_comments", return_value=[{"body": "s"}]),
    ):
        bodies, summaries = _mod._fetch_out_of_thread_notes("o", "r", 1, lambda p: [])
    assert bodies == []
    assert summaries == [{"body": "s"}]
    assert "could not fetch review bodies (rate limited)" in capsys.readouterr().err


@pytest.mark.parametrize(
    "message",
    ["secondary rate limit exceeded", "HTTP 502 Bad Gateway", "503 unavailable", "504 timeout"],
)
def test_main_refuses_resolved_blind_rest_on_transient_graphql_failure(
    monkeypatch, capsys, message
):
    """Falling back to REST here would re-surface already-resolved threads as
    unresolved — GraphQL is the only source of isResolved.

    GhTransportError, not a bare RuntimeError: only gh's own stderr can be
    transient. A plain RuntimeError carrying the same text is a permanent error
    whose message merely contains the marker, and it must reach REST instead.
    """
    monkeypatch.setattr(sys, "argv", ["fetch-pr-comments.py", "owner", "repo", "1"])
    monkeypatch.setattr(_mod, "_gh_available", lambda: True)
    monkeypatch.setattr(
        _mod, "fetch_graphql", MagicMock(side_effect=_mod.GhTransportError(message))
    )
    rest = MagicMock(return_value=[])
    monkeypatch.setattr(_mod, "fetch_rest_gh", rest)

    with pytest.raises(SystemExit) as exc:
        _mod.main()
    assert exc.value.code == 1
    assert "retry rather than fall back to resolved-blind REST" in capsys.readouterr().err
    rest.assert_not_called()


# ── transient vs permanent classification (review-1a6a54b6) ───────────────────
#
# The marker scan runs on gh's own stderr only. Permanent errors interpolate the
# PR number and owner/repo, so an unguarded substring test read "PR #502 not
# found" as a 502 and told the caller to retry a condition that never clears.


@pytest.mark.parametrize(
    "message",
    [
        "PR #502 not found in acme/webapp",
        "PR #1502 not found in acme/webapp",
        "PR #2504 not found in acme/webapp",
        "PR #7 not found in acme/secondary-index",
        "PR #7 not found in acme/service-503",
        '[{"message": "Could not resolve to a Repository with the name \'acme/api-502\'."}]',
    ],
)
def test_permanent_error_carrying_a_transient_marker_falls_back_to_rest(
    monkeypatch, capsys, message
):
    """A permanent RuntimeError must reach the REST fallback even when its text
    happens to contain 502/503/504/secondary."""
    monkeypatch.setattr(sys, "argv", ["fetch-pr-comments.py", "acme", "webapp", "502"])
    monkeypatch.setattr(_mod, "_gh_available", lambda: True)
    monkeypatch.setattr(_mod, "fetch_graphql", MagicMock(side_effect=RuntimeError(message)))
    rest = MagicMock(return_value=[])
    monkeypatch.setattr(_mod, "fetch_rest_gh", rest)
    monkeypatch.setattr(_mod, "_fetch_out_of_thread_notes", lambda *a: ([], []))

    _mod.main()  # no SystemExit
    rest.assert_called_once()
    err = capsys.readouterr().err
    assert "falling back to REST" in err
    assert "transiently unavailable" not in err


def test_gh_transport_error_without_a_transient_marker_falls_back(monkeypatch, capsys):
    """A gh failure that is not rate-limit/5xx is permanent — REST, not exit."""
    monkeypatch.setattr(sys, "argv", ["fetch-pr-comments.py", "acme", "webapp", "1"])
    monkeypatch.setattr(_mod, "_gh_available", lambda: True)
    monkeypatch.setattr(
        _mod, "fetch_graphql", MagicMock(side_effect=_mod.GhTransportError("HTTP 404 Not Found"))
    )
    rest = MagicMock(return_value=[])
    monkeypatch.setattr(_mod, "fetch_rest_gh", rest)
    monkeypatch.setattr(_mod, "_fetch_out_of_thread_notes", lambda *a: ([], []))

    _mod.main()
    rest.assert_called_once()


def test_gh_helpers_raise_the_transport_subclass():
    """Both gh call sites must raise GhTransportError, or the guard above sees a
    plain RuntimeError and a genuine outage stops hard-failing."""
    for fn, args in ((_mod._gh_graphql, ("q", {})), (_mod._gh_rest_paginate, ("some/path",))):
        with (
            patch("subprocess.run", return_value=_proc(returncode=1, stderr=b"HTTP 502")),
            pytest.raises(_mod.GhTransportError, match="502"),
        ):
            fn(*args)


def test_rate_limited_graphql_payload_is_typed_transient():
    """GitHub types rate-limit errors; match the field, not the rendered text."""
    resp = {"errors": [{"type": "RATE_LIMITED", "message": "API rate limit exceeded"}]}
    with (
        patch.object(_mod, "_gh_graphql", return_value=resp),
        pytest.raises(_mod.GhTransportError, match="RATE_LIMITED"),
    ):
        fetch_graphql("acme", "webapp", 1)


def test_non_rate_limited_graphql_payload_stays_permanent():
    resp = {"errors": [{"type": "NOT_FOUND", "message": "Could not resolve to a Repository"}]}
    with patch.object(_mod, "_gh_graphql", return_value=resp), pytest.raises(RuntimeError) as exc:
        fetch_graphql("acme", "webapp", 1)
    assert not isinstance(exc.value, _mod.GhTransportError)


def test_malformed_errors_payload_does_not_crash_the_type_check():
    """`errors` is server-controlled; a non-list or non-dict entry must not raise
    an AttributeError inside the classifier."""
    for payload in ({"errors": "boom"}, {"errors": ["boom"]}, {"errors": [None]}):
        with patch.object(_mod, "_gh_graphql", return_value=payload), pytest.raises(RuntimeError):
            fetch_graphql("acme", "webapp", 1)


def test_module_runs_as_a_script(monkeypatch, capsys):
    """Covers the `if __name__ == '__main__'` body — the only wiring to main()."""
    monkeypatch.setattr(sys, "argv", ["fetch-pr-comments.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 2
    assert "Usage: fetch-pr-comments.py" in capsys.readouterr().err
