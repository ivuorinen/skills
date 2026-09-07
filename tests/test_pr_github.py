"""Tests for skills/nitpicker/scripts/pr_github.py.

Supersedes tests/test_fetch_pr_comments.py: the GitHub logic moved out of the
hyphenated entry point into this importable provider when the fetchers grew
GitLab and Bitbucket siblings. The behaviours pinned here are the ones whose
breakage is silent — a GraphQL fallback that downgrades on a transient error
re-surfaces resolved threads as unresolved, and a token sent to the wrong host
still returns a plausible-looking result.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pr_common as c  # type: ignore[import-not-found]  # noqa: E402
import pr_github as gh  # type: ignore[import-not-found]  # noqa: E402

_TARGET = c.Target("github", "github.com", "owner/repo")
_GHES = c.Target("github", "ghe.acme.com", "owner/repo")


def _proc(stdout=b"", returncode=0, stderr=b"") -> MagicMock:
    p = MagicMock(spec=subprocess.CompletedProcess)
    p.stdout = stdout
    p.returncode = returncode
    p.stderr = stderr
    return p


def _thread_node(node_id="T_1", resolved=False, comments=None, has_next=False, path="src/f.py"):
    return {
        "id": node_id,
        "isResolved": resolved,
        "path": path,
        "line": 12,
        "comments": {
            "pageInfo": {"hasNextPage": has_next, "endCursor": "c1" if has_next else None},
            "nodes": comments
            if comments is not None
            else [
                {
                    "id": "C_1",
                    "body": "fix this",
                    "createdAt": "2024-01-01",
                    "url": "https://github.com/owner/repo/pull/1#c1",
                    "author": {"login": "reviewer"},
                    "diffHunk": "@@ -1 +1 @@",
                }
            ],
        },
    }


def _graphql_response(nodes, has_next=False):
    return {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "pageInfo": {"hasNextPage": has_next, "endCursor": "p1"},
                        "nodes": nodes,
                    }
                }
            }
        }
    }


# ── transports ────────────────────────────────────────────────────────────────


class TestGhTransports:
    def test_gh_available_delegates_to_the_shared_probe(self):
        with patch.object(c, "cli_available", return_value=True) as probe:
            assert gh._gh_available() is True
        assert probe.call_args[0][0] == "gh"

    def test_graphql_success_returns_parsed_json(self):
        with patch.object(subprocess, "run", return_value=_proc(stdout=b'{"data": {}}')):
            assert gh._gh_graphql("query", {}) == {"data": {}}

    def test_graphql_nonzero_raises_transport_error_carrying_stderr(self):
        with (
            patch.object(subprocess, "run", return_value=_proc(returncode=1, stderr=b"boom")),
            pytest.raises(gh.GhTransportError, match="boom"),
        ):
            gh._gh_graphql("query", {})

    def test_graphql_passes_hostname_for_enterprise(self):
        """The host must be the value of `--hostname`, not merely present in argv.

        Asserting membership alone passes if the host reaches argv by any route
        — as part of a URL, or after some other flag — which is the case that
        would actually send a token somewhere unintended.
        """
        with patch.object(subprocess, "run", return_value=_proc(stdout=b"{}")) as run:
            gh._gh_graphql("query", {}, "ghe.acme.com")
        argv = run.call_args[0][0]
        assert argv[argv.index("--hostname") + 1] == "ghe.acme.com"

    def test_rest_paginate_flattens_slurped_pages(self):
        with patch.object(subprocess, "run", return_value=_proc(stdout=b"[[1,2],[3]]")) as run:
            assert gh._gh_rest_paginate("repos/o/r/x") == [1, 2, 3]
        assert "--slurp" in run.call_args[0][0]
        assert "--paginate" in run.call_args[0][0]

    def test_rest_paginate_hostname_for_enterprise(self):
        """Same contract as the GraphQL path: the host is `--hostname`'s value."""
        with patch.object(subprocess, "run", return_value=_proc(stdout=b"[[]]")) as run:
            gh._gh_rest_paginate("repos/o/r/x", "ghe.acme.com")
        argv = run.call_args[0][0]
        assert argv[argv.index("--hostname") + 1] == "ghe.acme.com"

    def test_rest_paginate_keeps_object_pages_whole(self):
        """`--slurp` page shape follows the endpoint, and flattening a dict
        iterates its keys.

        /check-runs and /status return objects, not arrays. The old flatten
        turned a page into the strings "total_count"/"check_runs", so `_checks`
        found no dicts and reported zero CI checks on every gh-transport fetch.
        """
        page = {"total_count": 2, "check_runs": [{"name": "Validate"}, {"name": "Codacy"}]}
        with patch.object(
            subprocess, "run", return_value=_proc(stdout=json.dumps([page]).encode())
        ):
            out = gh._gh_rest_paginate("repos/o/r/commits/sha/check-runs")
        assert out == [page]
        assert all(isinstance(x, dict) for x in out)

    def test_rest_paginate_still_flattens_array_pages(self):
        # The five array-valued endpoints must keep their old behaviour.
        pages = [[{"id": 1}, {"id": 2}], [{"id": 3}]]
        with patch.object(subprocess, "run", return_value=_proc(stdout=json.dumps(pages).encode())):
            assert gh._gh_rest_paginate("repos/o/r/pulls/1/comments") == [
                {"id": 1},
                {"id": 2},
                {"id": 3},
            ]

    def test_checks_are_found_through_the_real_gh_transport(self):
        """End to end over `_gh_rest_paginate`, not a mocked `rest_list`.

        Every existing check test injected `rest_list` directly, which is why a
        defect in the layer beneath it survived a 100%-covered suite.
        """
        runs = {
            "total_count": 1,
            "check_runs": [{"name": "Validate", "status": "completed", "conclusion": "success"}],
        }
        statuses = {"state": "success", "statuses": []}

        def fake_run(argv, *a, **k):
            body = runs if "check-runs" in argv[-1] else statuses
            return _proc(stdout=json.dumps([body]).encode())

        with patch.object(subprocess, "run", side_effect=fake_run):
            checks = gh._checks(_TARGET, "sha", gh._gh_transport(_TARGET))
        assert [c["name"] for c in checks] == ["Validate"]
        assert c.summarize_checks(checks)["success"] == 1

    def test_rest_paginate_nonzero_raises(self):
        with (
            patch.object(subprocess, "run", return_value=_proc(returncode=1, stderr=b"nope")),
            pytest.raises(gh.GhTransportError, match="nope"),
        ):
            gh._gh_rest_paginate("repos/o/r/x")

    def test_token_transport_hits_the_pinned_api_host(self):
        with patch.object(c, "paginate_link", return_value=[{"x": 1}]) as paginate:
            out = gh._token_transport(_TARGET, "tok")("repos/o/r/pulls/1/reviews")
        assert out == [{"x": 1}]
        assert paginate.call_args[0][0].startswith("https://api.github.com/repos/o/r/")
        assert paginate.call_args[0][1]["Authorization"] == "token tok"
        assert paginate.call_args[0][2] == "api.github.com"

    def test_token_get_returns_the_body(self):
        with patch.object(c, "http_json", return_value=({"number": 1}, {})):
            assert gh._token_get(_TARGET, "tok", "repos/o/r/pulls/1") == {"number": 1}


class TestTokenHostGuard:
    """A github.com token must never be forwarded to an Enterprise host — that is
    a credential handed to a third party, not a failed request."""

    def test_token_used_on_github_com(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        assert gh._token_for(_TARGET) == "tok"

    def test_token_withheld_from_an_undeclared_enterprise_host(self, monkeypatch, capsys):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        monkeypatch.delenv("GH_HOST", raising=False)
        assert gh._token_for(_GHES) == ""
        assert "not declared for ghe.acme.com" in capsys.readouterr().err

    def test_token_used_when_gh_host_declares_that_instance(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        monkeypatch.setenv("GH_HOST", "GHE.acme.com")
        assert gh._token_for(_GHES) == "tok"

    def test_absent_token_stays_absent(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert gh._token_for(_GHES) == ""


class TestTransportSelection:
    def test_gh_preferred_when_available(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with patch.object(gh, "_gh_available", return_value=True):
            _list, get_one, label = gh._transport(_TARGET)
        assert label == "gh"
        with patch.object(c, "cli_json", return_value={"ok": 1}) as cli:
            assert get_one("repos/o/r/pulls/1") == {"ok": 1}
        assert cli.call_args[0][0][:2] == ["gh", "api"]

    def test_gh_get_passes_hostname_for_enterprise(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        monkeypatch.setenv("GH_HOST", "ghe.acme.com")
        with patch.object(gh, "_gh_available", return_value=True):
            _list, get_one, _label = gh._transport(_GHES)
        with patch.object(c, "cli_json", return_value={}) as cli:
            get_one("repos/o/r/pulls/1")
        assert "--hostname" in cli.call_args[0][0]

    def test_token_used_when_gh_absent(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        with patch.object(gh, "_gh_available", return_value=False):
            _list, _get, label = gh._transport(_TARGET)
        assert label == "token"

    def test_no_auth_raises(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with (
            patch.object(gh, "_gh_available", return_value=False),
            pytest.raises(c.TransportError, match="No auth"),
        ):
            gh._transport(_TARGET)


# ── GraphQL thread fetch ──────────────────────────────────────────────────────


class TestFetchGraphql:
    def test_unresolved_thread_returned_in_the_shared_shape(self):
        with patch.object(gh, "_gh_graphql", return_value=_graphql_response([_thread_node()])):
            threads = gh.fetch_graphql(_TARGET, 1)
        assert len(threads) == 1
        assert threads[0]["thread_id"] == "T_1"
        assert threads[0]["path"] == "src/f.py"
        assert threads[0]["line"] == 12
        assert threads[0]["is_resolved"] is False
        assert threads[0]["diff_hunk"] == "@@ -1 +1 @@"
        assert threads[0]["comments"][0]["author"] == "reviewer"

    def test_resolved_thread_excluded(self):
        with patch.object(
            gh, "_gh_graphql", return_value=_graphql_response([_thread_node(resolved=True)])
        ):
            assert gh.fetch_graphql(_TARGET, 1) == []

    def test_outer_pagination_follows_the_cursor(self):
        pages = [
            _graphql_response([_thread_node("T_1")], has_next=True),
            _graphql_response([_thread_node("T_2")]),
        ]
        with patch.object(gh, "_gh_graphql", side_effect=pages):
            assert [t["thread_id"] for t in gh.fetch_graphql(_TARGET, 1)] == ["T_1", "T_2"]

    def test_inner_comment_pagination_fetches_every_page(self):
        # A thread with >100 comments must not be truncated to its first page.
        first = _graphql_response([_thread_node(has_next=True)])
        more = {
            "data": {
                "node": {
                    "comments": {
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "C_2",
                                "body": "and this",
                                "createdAt": "2024-01-02",
                                "url": "",
                                "author": {"login": "reviewer"},
                                "diffHunk": "",
                            }
                        ],
                    }
                }
            }
        }
        with patch.object(gh, "_gh_graphql", side_effect=[first, more]):
            threads = gh.fetch_graphql(_TARGET, 1)
        assert [x["id"] for x in threads[0]["comments"]] == ["C_1", "C_2"]

    def test_thread_deleted_mid_inner_pagination_keeps_what_was_read(self):
        first = _graphql_response([_thread_node(has_next=True)])
        with patch.object(gh, "_gh_graphql", side_effect=[first, {"data": {"node": None}}]):
            threads = gh.fetch_graphql(_TARGET, 1)
        assert len(threads[0]["comments"]) == 1

    def test_inner_pagination_errors_raise(self):
        first = _graphql_response([_thread_node(has_next=True)])
        with (
            patch.object(gh, "_gh_graphql", side_effect=[first, {"errors": [{"message": "x"}]}]),
            pytest.raises(RuntimeError),
        ):
            gh.fetch_graphql(_TARGET, 1)

    def test_empty_comments_node_yields_empty_hunk(self):
        with patch.object(
            gh, "_gh_graphql", return_value=_graphql_response([_thread_node(comments=[])])
        ):
            threads = gh.fetch_graphql(_TARGET, 1)
        assert threads[0]["diff_hunk"] == "" and threads[0]["url"] == ""

    def test_null_author_becomes_unknown(self):
        node = _thread_node(
            comments=[
                {
                    "id": "C",
                    "body": "b",
                    "createdAt": "t",
                    "url": "",
                    "author": None,
                    "diffHunk": "",
                }
            ]
        )
        with patch.object(gh, "_gh_graphql", return_value=_graphql_response([node])):
            assert gh.fetch_graphql(_TARGET, 1)[0]["comments"][0]["author"] == "unknown"

    def test_rate_limited_errors_raise_the_transport_type(self):
        # Typed on the GraphQL field, not the rendered text: the payload echoes
        # the repository name, so a repo called `api-502` would read as a 502.
        with (
            patch.object(gh, "_gh_graphql", return_value={"errors": [{"type": "RATE_LIMITED"}]}),
            pytest.raises(gh.GhTransportError),
        ):
            gh.fetch_graphql(_TARGET, 1)

    def test_other_errors_raise_plain_runtime_error(self):
        with (
            patch.object(gh, "_gh_graphql", return_value={"errors": [{"message": "nope"}]}),
            pytest.raises(RuntimeError) as exc,
        ):
            gh.fetch_graphql(_TARGET, 1)
        assert not isinstance(exc.value, gh.GhTransportError)

    def test_non_list_errors_field_still_raises(self):
        with (
            patch.object(gh, "_gh_graphql", return_value={"errors": "broken"}),
            pytest.raises(RuntimeError),
        ):
            gh.fetch_graphql(_TARGET, 1)

    def test_missing_pr_raises_not_found(self):
        response = {"data": {"repository": {"pullRequest": None}}}
        with (
            patch.object(gh, "_gh_graphql", return_value=response),
            pytest.raises(RuntimeError, match="not found"),
        ):
            gh.fetch_graphql(_TARGET, 1)


# ── REST grouping ─────────────────────────────────────────────────────────────


class TestGroupRestComments:
    def test_empty(self):
        assert gh._group_rest_comments([]) == []

    def test_single_root_comment_becomes_a_thread_of_unknown_resolution(self):
        threads = gh._group_rest_comments(
            [
                {
                    "id": 1,
                    "path": "f.py",
                    "line": 3,
                    "diff_hunk": "@@",
                    "body": "b",
                    "created_at": "t",
                    "html_url": "u",
                    "user": {"login": "rev"},
                }
            ]
        )
        assert len(threads) == 1
        # REST cannot report resolution; null obliges the caller to check the code.
        assert threads[0]["is_resolved"] is None
        assert threads[0]["comments"][0]["author"] == "rev"

    def test_reply_is_grouped_with_its_parent(self):
        raw = [
            {"id": 1, "path": "f.py", "body": "a", "user": {"login": "x"}},
            {"id": 2, "in_reply_to_id": 1, "body": "b", "user": {"login": "y"}},
        ]
        threads = gh._group_rest_comments(raw)
        assert len(threads) == 1 and len(threads[0]["comments"]) == 2

    def test_separate_roots_are_separate_threads(self):
        raw = [
            {"id": 1, "path": "a.py", "body": "a", "user": {"login": "x"}},
            {"id": 2, "path": "b.py", "body": "b", "user": {"login": "y"}},
        ]
        assert len(gh._group_rest_comments(raw)) == 2

    def test_missing_user_becomes_unknown(self):
        threads = gh._group_rest_comments([{"id": 1, "body": "b", "user": None}])
        assert threads[0]["comments"][0]["author"] == "unknown"

    def test_fetch_rest_calls_the_comments_endpoint(self):
        rest = MagicMock(return_value=[])
        gh.fetch_rest(_TARGET, 7, rest)
        assert rest.call_args[0][0] == "repos/owner/repo/pulls/7/comments"


# ── out-of-thread notes ───────────────────────────────────────────────────────


class TestOutOfThreadNotes:
    def test_review_bodies_keep_non_empty_bodies_from_any_author(self):
        rest = MagicMock(
            return_value=[
                {
                    "user": {"login": "coderabbitai"},
                    "state": "COMMENTED",
                    "commit_id": "abcdef1234567890",
                    "submitted_at": "t",
                    "body": "outside diff range",
                },
                {"user": {"login": "x"}, "body": "   "},
                {"user": {"login": "y"}, "body": None},
                "not-a-dict",
            ]
        )
        bodies = gh._fetch_review_bodies(_TARGET, 1, rest)
        assert len(bodies) == 1
        assert bodies[0]["commit_id"] == "abcdef123456"  # truncated to 12

    def test_summary_comments_are_not_filtered_to_bots(self):
        # Filtering to `[bot]` logins dropped a maintainer's plain PR comment
        # entirely, so `cr` could neither act on it nor record a verdict.
        rest = MagicMock(
            return_value=[
                {"user": {"login": "coderabbitai"}, "body": "summary", "created_at": "t"},
                {"user": {"login": "a-human"}, "body": "also fix the sibling", "updated_at": "u"},
                {"user": {"login": "z"}, "body": ""},
            ]
        )
        authors = [x["author"] for x in gh._fetch_summary_comments(_TARGET, 1, rest)]
        assert authors == ["coderabbitai", "a-human"]

    def test_each_half_survives_the_others_failure(self, capsys):
        # The outside-diff-range comments in review_bodies are what this fetch
        # exists to surface, so they must survive a summary-comment failure.
        def rest(path):
            if "issues" in path:
                raise RuntimeError("rate limited")
            return [{"user": {"login": "r"}, "body": "kept"}]

        bodies, summaries = gh._out_of_thread_notes(_TARGET, 1, rest)
        assert len(bodies) == 1 and summaries == []
        assert "summary comments" in capsys.readouterr().err


# ── fetch_comments orchestration ──────────────────────────────────────────────


class TestFetchComments:
    _THREADS: ClassVar[list[dict]] = [c.thread(thread_id="T_1", path="f.py", is_resolved=False)]

    @pytest.fixture(autouse=True)
    def _stub_notes(self):
        with patch.object(gh, "_out_of_thread_notes", return_value=([], [])):
            yield

    def test_graphql_path_labels_its_transport(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with (
            patch.object(gh, "_gh_available", return_value=True),
            patch.object(gh, "fetch_graphql", return_value=self._THREADS),
        ):
            out = gh.fetch_comments(_TARGET, 1)
        assert out["transport"] == "gh-graphql"
        assert out["platform"] == "github" and out["repo"] == "owner/repo"
        assert set(out) >= {"threads", "review_bodies", "summary_comments"}

    @pytest.mark.parametrize(
        "message",
        ["rate limit exceeded", "secondary rate limit", "server error 502", "503", "504"],
    )
    def test_transient_graphql_failure_aborts_instead_of_downgrading(self, message, monkeypatch):
        # REST cannot report resolution, so a transient GraphQL error must not
        # silently fall back — that re-surfaces resolved threads as unresolved.
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with (
            patch.object(gh, "_gh_available", return_value=True),
            patch.object(gh, "fetch_graphql", side_effect=gh.GhTransportError(message)),
            pytest.raises(c.TransportError, match="retry rather than fall back"),
        ):
            gh.fetch_comments(_TARGET, 1)

    def test_graphql_timeout_is_classified_transient(self, monkeypatch):
        # TimeoutExpired subclasses SubprocessError, so it matches neither the
        # `except (RuntimeError, OSError)` clause nor `_is_transient`'s
        # GhTransportError check. Without its own clause it escapes as a bare
        # "timed out after 30 seconds", telling the caller nothing about retrying.
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with (
            patch.object(gh, "_gh_available", return_value=True),
            patch.object(gh, "fetch_graphql", side_effect=subprocess.TimeoutExpired("gh", 30)),
            pytest.raises(c.TransportError, match="retry rather than fall back"),
        ):
            gh.fetch_comments(_TARGET, 1)

    def test_graphql_timeout_never_downgrades_to_rest(self, monkeypatch):
        # The hazard the classification exists to prevent: REST cannot report
        # resolution, so falling back re-surfaces resolved threads as unresolved.
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        with (
            patch.object(gh, "_gh_available", return_value=True),
            patch.object(gh, "fetch_graphql", side_effect=subprocess.TimeoutExpired("gh", 30)),
            patch.object(gh, "fetch_rest") as rest,
            pytest.raises(c.TransportError),
        ):
            gh.fetch_comments(_TARGET, 1)
        rest.assert_not_called()

    def test_permanent_graphql_failure_falls_back_to_rest(self, monkeypatch, capsys):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with (
            patch.object(gh, "_gh_available", return_value=True),
            patch.object(gh, "fetch_graphql", side_effect=RuntimeError("PR #502 not found")),
            patch.object(gh, "fetch_rest", return_value=self._THREADS),
        ):
            out = gh.fetch_comments(_TARGET, 1)
        # "502" appears in the PR number; a marker scan not confined to
        # GhTransportError would call this transient and loop forever.
        assert out["transport"] == "gh-rest"
        assert "falling back to REST" in capsys.readouterr().err

    def test_gh_rest_failure_without_a_token_raises(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with (
            patch.object(gh, "_gh_available", return_value=True),
            patch.object(gh, "fetch_graphql", side_effect=RuntimeError("gql")),
            patch.object(gh, "fetch_rest", side_effect=RuntimeError("rest")),
            pytest.raises(c.TransportError, match="gh REST failed"),
        ):
            gh.fetch_comments(_TARGET, 1)

    def test_gh_rest_failure_falls_through_to_the_token(self, monkeypatch, capsys):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        with (
            patch.object(gh, "_gh_available", return_value=True),
            patch.object(gh, "fetch_graphql", side_effect=RuntimeError("gql")),
            patch.object(gh, "fetch_rest", side_effect=[RuntimeError("rest"), self._THREADS]),
        ):
            out = gh.fetch_comments(_TARGET, 1)
        assert out["transport"] == "token-rest"
        assert "falling back to token REST" in capsys.readouterr().err

    def test_no_gh_with_token_uses_rest(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        with (
            patch.object(gh, "_gh_available", return_value=False),
            patch.object(gh, "fetch_rest", return_value=self._THREADS),
        ):
            assert gh.fetch_comments(_TARGET, 1)["transport"] == "token-rest"

    def test_no_gh_no_token_raises(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with (
            patch.object(gh, "_gh_available", return_value=False),
            pytest.raises(c.TransportError, match="No auth"),
        ):
            gh.fetch_comments(_TARGET, 1)

    def test_notes_reuse_the_transport_that_fetched_the_threads(self, monkeypatch):
        # A gh path that failed into token REST must not silently re-select a
        # broken gh for the notes.
        monkeypatch.setenv("GITHUB_TOKEN", "tok")
        captured = {}

        def capture(_t, _n, rest_list):
            captured["rest"] = rest_list
            return ([], [])

        token_rest = MagicMock(name="token_rest")
        with (
            patch.object(gh, "_gh_available", return_value=True),
            patch.object(gh, "fetch_graphql", side_effect=RuntimeError("gql")),
            patch.object(gh, "fetch_rest", side_effect=[RuntimeError("rest"), self._THREADS]),
            patch.object(gh, "_token_transport", return_value=token_rest),
            patch.object(gh, "_out_of_thread_notes", side_effect=capture),
        ):
            gh.fetch_comments(_TARGET, 1)
        assert captured["rest"] is token_rest


# ── status ────────────────────────────────────────────────────────────────────


class TestChecks:
    def test_check_runs_and_legacy_statuses_are_both_reported(self):
        # Reading only /check-runs reports a green PR that uses the older
        # statuses API as having no CI at all.
        def rest(path):
            if "check-runs" in path:
                return [
                    {
                        "check_runs": [
                            {
                                "name": "build",
                                "status": "completed",
                                "conclusion": "success",
                                "html_url": "u",
                            }
                        ]
                    }
                ]
            return [{"statuses": [{"context": "legacy", "state": "failure", "target_url": "v"}]}]

        checks = gh._checks(_TARGET, "sha", rest)
        assert [x["name"] for x in checks] == ["build", "legacy"]
        assert checks[1]["status"] == "completed" and checks[1]["conclusion"] == "failure"

    def test_pending_legacy_status_is_in_progress(self):
        def rest(path):
            if "check-runs" in path:
                return []
            return [{"statuses": [{"context": "slow", "state": "pending"}]}]

        assert gh._checks(_TARGET, "sha", rest)[0]["status"] == "in_progress"

    def test_non_dict_pages_are_skipped(self):
        assert gh._checks(_TARGET, "sha", lambda _p: ["junk"]) == []


class TestReviews:
    def test_latest_verdict_per_reviewer_wins(self):
        # A reviewer who requested changes and then approved appears twice;
        # counting raw rows reports the PR as still blocked.
        rest = MagicMock(
            return_value=[
                {"user": {"login": "a"}, "state": "CHANGES_REQUESTED", "submitted_at": "1"},
                {"user": {"login": "a"}, "state": "APPROVED", "submitted_at": "2"},
            ]
        )
        reviews = gh._reviews(_TARGET, 1, rest)
        assert reviews == [c.review(author="a", state="approved", submitted_at="2")]

    def test_commented_never_supersedes_a_verdict(self):
        rest = MagicMock(
            return_value=[
                {"user": {"login": "a"}, "state": "APPROVED", "submitted_at": "1"},
                {"user": {"login": "a"}, "state": "COMMENTED", "submitted_at": "2"},
            ]
        )
        assert gh._reviews(_TARGET, 1, rest)[0]["state"] == "approved"

    def test_commented_alone_is_kept(self):
        rest = MagicMock(return_value=[{"user": {"login": "a"}, "state": "COMMENTED"}])
        assert gh._reviews(_TARGET, 1, rest)[0]["state"] == "commented"

    def test_pending_and_dismissed_carry_no_verdict(self):
        rest = MagicMock(
            return_value=[
                {"user": {"login": "a"}, "state": "PENDING"},
                {"user": {"login": "b"}, "state": "DISMISSED"},
                "junk",
            ]
        )
        assert gh._reviews(_TARGET, 1, rest) == []


class TestFetchStatus:
    _PR: ClassVar[dict] = {
        "number": 42,
        "html_url": "https://github.com/owner/repo/pull/42",
        "title": "Add thing",
        "user": {"login": "author"},
        "state": "open",
        "draft": True,
        "head": {"ref": "feat/x", "sha": "deadbeef"},
        "base": {"ref": "main"},
        "created_at": "c",
        "updated_at": "u",
        "mergeable": True,
        "mergeable_state": "clean",
    }

    def _run(self, pr, **patches):
        rest = patches.pop("rest", MagicMock(return_value=[]))
        with patch.object(gh, "_transport", return_value=(rest, lambda _p: pr, "gh")):
            return gh.fetch_status(_TARGET, 42)

    def test_maps_every_envelope_field(self):
        with (
            patch.object(gh, "_checks", return_value=[]),
            patch.object(gh, "_reviews", return_value=[]),
        ):
            out = self._run(self._PR)
        assert out["state"] == "open"
        assert out["is_draft"] is True
        assert out["source_branch"] == "feat/x" and out["target_branch"] == "main"
        assert out["head_sha"] == "deadbeef"
        assert out["mergeable"] is True and out["merge_state"] == "clean"
        assert out["platform"] == "github"

    def test_merged_pr_reports_merged_not_closed(self):
        merged = {**self._PR, "state": "closed", "merged": True}
        with (
            patch.object(gh, "_checks", return_value=[]),
            patch.object(gh, "_reviews", return_value=[]),
        ):
            assert self._run(merged)["state"] == "merged"

    def test_changed_files_are_flattened_to_paths(self):
        rest = MagicMock(return_value=[{"filename": "a.py"}, {"filename": "b.py"}, "junk"])
        with (
            patch.object(gh, "_checks", return_value=[]),
            patch.object(gh, "_reviews", return_value=[]),
        ):
            out = self._run(self._PR, rest=rest)
        assert out["changed_files"] == ["a.py", "b.py"]

    def test_checks_skipped_when_there_is_no_head_sha(self):
        no_sha = {**self._PR, "head": {"ref": "x"}}
        with (
            patch.object(gh, "_checks") as checks,
            patch.object(gh, "_reviews", return_value=[]),
        ):
            assert self._run(no_sha)["checks"] == []
        checks.assert_not_called()

    def test_secondary_fetch_failure_degrades_rather_than_losing_the_pr(self, capsys):
        with (
            patch.object(gh, "_checks", side_effect=RuntimeError("ci down")),
            patch.object(gh, "_reviews", side_effect=RuntimeError("reviews down")),
        ):
            out = self._run(self._PR)
        assert out["title"] == "Add thing"
        assert out["checks"] == [] and out["reviews"] == []
        assert "ci down" in capsys.readouterr().err

    def test_missing_pr_raises(self):
        with pytest.raises(c.TransportError, match="not found"):
            self._run({"message": "Not Found"})


def test_provider_is_reachable_through_the_shared_dispatcher():
    assert c.provider_for(_TARGET) is gh


@pytest.mark.parametrize(
    "module", ["pr_common.py", "pr_github.py", "pr_gitlab.py", "pr_bitbucket.py"]
)
def test_module_emits_nothing_to_stdout_on_import(module, capsys):
    """mcp_server imports all four transitively and its stdout carries only
    JSON-RPC frames, so a stray print in any of them corrupts the stream.

    The import happens *inside* the test. Asserting on a module imported at file
    scope would pass whatever the module did, because that import already ran
    during collection — the assertion would hold by construction.
    """
    spec = importlib.util.spec_from_file_location(f"probe_{module}", _SCRIPTS / module)
    assert spec is not None
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)  # type: ignore[union-attr]
    assert capsys.readouterr().out == ""
