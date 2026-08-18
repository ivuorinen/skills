"""Tests for skills/nitpicker/scripts/pr_bitbucket.py.

Bitbucket's comment feed is flat: inline threads, replies, and PR-level comments
arrive from one endpoint distinguished only by an `inline` anchor and a `parent`
id. Reassembling that into threads is where a deep reply chain silently splits,
so the threading rules are pinned here alongside the state mappings.
"""

import base64
import sys
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pr_bitbucket as bb  # type: ignore[import-not-found]  # noqa: E402
import pr_common as c  # type: ignore[import-not-found]  # noqa: E402

_TARGET = c.Target("bitbucket", "bitbucket.org", "ws/repo")


def _comment(cid, body="fix", inline=None, parent=None, **extra):
    record = {
        "id": cid,
        "content": {"raw": body},
        "user": {"nickname": "reviewer"},
        "created_on": "2024-01-01",
        "updated_on": "2024-01-02",
        "links": {"html": {"href": f"https://bitbucket.org/ws/repo/pull-requests/1#comment-{cid}"}},
        **extra,
    }
    if inline is not None:
        record["inline"] = inline
    if parent is not None:
        record["parent"] = {"id": parent}
    return record


# ── auth ──────────────────────────────────────────────────────────────────────


class TestHeaders:
    def test_token_is_sent_as_bearer(self, monkeypatch):
        monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
        assert bb._headers()["Authorization"] == "Bearer tok"

    def test_username_and_app_password_become_basic(self, monkeypatch):
        monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
        monkeypatch.setenv("BITBUCKET_USERNAME", "u")
        monkeypatch.setenv("BITBUCKET_APP_PASSWORD", "p")
        expected = base64.b64encode(b"u:p").decode()
        assert bb._headers()["Authorization"] == f"Basic {expected}"

    def test_token_wins_over_basic(self, monkeypatch):
        monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
        monkeypatch.setenv("BITBUCKET_USERNAME", "u")
        monkeypatch.setenv("BITBUCKET_APP_PASSWORD", "p")
        assert bb._headers()["Authorization"].startswith("Bearer")

    @pytest.mark.parametrize(
        "env", [{}, {"BITBUCKET_USERNAME": "u"}, {"BITBUCKET_APP_PASSWORD": "p"}]
    )
    def test_missing_or_half_credentials_raise(self, env, monkeypatch):
        for name in ("BITBUCKET_TOKEN", "BITBUCKET_USERNAME", "BITBUCKET_APP_PASSWORD"):
            monkeypatch.delenv(name, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        with pytest.raises(c.TransportError, match="BITBUCKET_TOKEN"):
            bb._headers()


class TestTransport:
    def test_pins_the_bitbucket_api_host(self, monkeypatch):
        monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
        list_all, get_one = bb._transport(_TARGET)
        with patch.object(c, "paginate_body_next", return_value=[]) as paginate:
            list_all("repositories/ws/repo/pullrequests/1/comments")
        assert paginate.call_args[0][0].startswith("https://api.bitbucket.org/2.0/")
        assert "pagelen=100" in paginate.call_args[0][0]
        assert paginate.call_args[0][2] == "api.bitbucket.org"
        with patch.object(c, "http_json", return_value=({"id": 1}, {})):
            assert get_one("repositories/ws/repo/pullrequests/1") == {"id": 1}

    def test_pagelen_joins_an_existing_query_string(self, monkeypatch):
        monkeypatch.setenv("BITBUCKET_TOKEN", "tok")
        list_all, _get = bb._transport(_TARGET)
        with patch.object(c, "paginate_body_next", return_value=[]) as paginate:
            list_all("repositories/ws/repo/diffstat?fields=values")
        assert "?fields=values&pagelen=100" in paginate.call_args[0][0]


# ── comment threading ─────────────────────────────────────────────────────────


class TestSplitComments:
    def test_inline_comment_becomes_a_thread(self):
        raw = [_comment(1, inline={"path": "src/f.py", "to": 12}, resolution=None)]
        threads, summary = bb._split_comments(raw)
        assert summary == []
        assert threads[0]["thread_id"] == "1"
        assert threads[0]["path"] == "src/f.py"
        assert threads[0]["line"] == 12
        # Bitbucket reports a line anchor, not a hunk.
        assert threads[0]["diff_hunk"] == ""
        assert threads[0]["is_resolved"] is False

    def test_non_null_resolution_marks_the_thread_resolved(self):
        raw = [_comment(1, inline={"path": "f.py", "to": 1}, resolution={"type": "resolution"})]
        assert bb._split_comments(raw)[0][0]["is_resolved"] is True

    def test_absent_resolution_field_is_unknown_not_unresolved(self):
        # Older payloads omit the field entirely; that is genuinely unknown.
        raw = [_comment(1, inline={"path": "f.py", "to": 1})]
        assert bb._split_comments(raw)[0][0]["is_resolved"] is None

    def test_old_line_anchor_used_when_the_line_was_deleted(self):
        raw = [_comment(1, inline={"path": "gone.py", "to": None, "from": 4})]
        assert bb._split_comments(raw)[0][0]["line"] == 4

    def test_pr_level_comment_becomes_a_summary_comment(self):
        threads, summary = bb._split_comments([_comment(1, body="please rebase")])
        assert threads == []
        assert summary == [
            {
                "author": "reviewer",
                "created_at": "2024-01-01",
                "updated_at": "2024-01-02",
                "body": "please rebase",
            }
        ]

    def test_reply_is_grouped_with_its_inline_parent(self):
        raw = [
            _comment(1, inline={"path": "f.py", "to": 1}),
            _comment(2, body="done", parent=1),
        ]
        threads, summary = bb._split_comments(raw)
        assert summary == []
        assert len(threads) == 1
        assert [x["id"] for x in threads[0]["comments"]] == ["1", "2"]

    def test_reply_arriving_before_its_parent_still_joins_the_thread(self):
        # Arrival order is the server's choice; `sort=id` is a request, not a
        # guarantee. A single forward pass dropped this reply into
        # summary_comments, where it loses its `path` and cr's non-thread
        # lifecycle then refuses to act on it — a reviewer's follow-up going
        # silently unactionable because a page came back reordered.
        raw = [
            _comment(2, body="still not fixed", parent=1),
            _comment(1, inline={"path": "f.py", "to": 1}),
        ]
        threads, summary = bb._split_comments(raw)
        assert summary == []
        assert len(threads) == 1
        assert sorted(x["id"] for x in threads[0]["comments"]) == ["1", "2"]
        assert threads[0]["path"] == "f.py"

    def test_thread_metadata_comes_from_the_root_not_the_first_arrival(self):
        # Reading `resolution` off a reply would report the reply's state as the
        # whole thread's.
        raw = [
            _comment(2, body="reply", parent=1, resolution=None),
            _comment(1, inline={"path": "f.py", "to": 1}, resolution={"type": "resolution"}),
        ]
        threads, _summary = bb._split_comments(raw)
        assert threads[0]["is_resolved"] is True
        assert threads[0]["thread_id"] == "1"

    def test_a_parent_cycle_does_not_hang(self):
        # Ids come from the API; a self- or mutually-referencing parent would
        # otherwise spin the chain walk forever.
        raw = [
            _comment(1, inline={"path": "f.py", "to": 1}, parent=2),
            _comment(2, body="b", parent=1),
        ]
        threads, summary = bb._split_comments(raw)
        assert len(threads) + len(summary) >= 1

    def test_reply_to_a_reply_stays_in_the_same_thread(self):
        # Bitbucket allows nested replies; assuming a reply's parent is itself a
        # root silently splits a deep thread into several.
        raw = [
            _comment(1, inline={"path": "f.py", "to": 1}),
            _comment(2, body="a", parent=1),
            _comment(3, body="b", parent=2),
            _comment(4, body="c", parent=3),
        ]
        threads, _summary = bb._split_comments(raw)
        assert len(threads) == 1
        assert [x["id"] for x in threads[0]["comments"]] == ["1", "2", "3", "4"]

    def test_separate_inline_anchors_are_separate_threads(self):
        raw = [
            _comment(1, inline={"path": "a.py", "to": 1}),
            _comment(2, inline={"path": "b.py", "to": 2}),
        ]
        assert len(bb._split_comments(raw)[0]) == 2

    def test_deleted_comments_are_dropped(self):
        # Bitbucket keeps the record with a null body; an empty comment in a
        # thread reads as a reviewer saying nothing.
        raw = [_comment(1, inline={"path": "f.py", "to": 1}), _comment(2, parent=1, deleted=True)]
        threads, _ = bb._split_comments(raw)
        assert len(threads[0]["comments"]) == 1

    def test_blank_pr_level_comments_are_not_summary_comments(self):
        assert bb._split_comments([_comment(1, body="   ")]) == ([], [])

    def test_non_dict_records_are_skipped(self):
        assert bb._split_comments(["junk", None]) == ([], [])

    def test_missing_user_becomes_unknown(self):
        raw = [{"id": 1, "content": {"raw": "x"}, "user": None}]
        _threads, summary = bb._split_comments(raw)
        assert summary[0]["author"] == "unknown"

    def test_reply_whose_parent_is_missing_starts_its_own_thread(self):
        raw = [_comment(9, inline={"path": "f.py", "to": 1}, parent=404)]
        threads, _ = bb._split_comments(raw)
        assert threads[0]["thread_id"] == "9"


class TestFetchComments:
    def test_envelope_reports_the_platform_and_empty_review_bodies(self):
        with patch.object(bb, "_transport", return_value=(MagicMock(return_value=[]), None)):
            out = bb.fetch_comments(_TARGET, 3)
        assert out["platform"] == "bitbucket" and out["repo"] == "ws/repo"
        # Bitbucket has no review-body concept — reported empty, never absent.
        assert out["review_bodies"] == []
        assert out["transport"] == "bitbucket-rest"

    def test_calls_the_comments_endpoint_asking_for_id_order(self):
        # `sort=id` keeps parents ahead of replies in the common case;
        # `_split_comments` does not depend on it, but asking costs nothing.
        rest = MagicMock(return_value=[])
        with patch.object(bb, "_transport", return_value=(rest, None)):
            bb.fetch_comments(_TARGET, 3)
        assert rest.call_args[0][0] == "repositories/ws/repo/pullrequests/3/comments?sort=id"


# ── status ────────────────────────────────────────────────────────────────────


class TestChecks:
    @pytest.mark.parametrize(
        "state, expected",
        [
            ("SUCCESSFUL", ("completed", "success")),
            ("FAILED", ("completed", "failure")),
            ("ERROR", ("completed", "failure")),
            ("STOPPED", ("completed", "cancelled")),
            ("INPROGRESS", ("in_progress", "")),
            ("SOMETHING_NEW", ("in_progress", "")),
        ],
    )
    def test_every_build_state_maps(self, state, expected):
        raw = [{"name": "build", "state": state, "url": "u"}]
        check = bb._checks(_TARGET, "sha", lambda _p: raw)[0]
        assert (check["status"], check["conclusion"]) == expected

    def test_key_is_the_fallback_name(self):
        raw = [{"key": "PIPELINE", "state": "SUCCESSFUL"}]
        assert bb._checks(_TARGET, "sha", lambda _p: raw)[0]["name"] == "PIPELINE"

    def test_non_dict_records_are_skipped(self):
        assert bb._checks(_TARGET, "sha", lambda _p: ["junk"]) == []

    def test_reads_the_commit_statuses_endpoint(self):
        rest = MagicMock(return_value=[])
        bb._checks(_TARGET, "abc123", rest)
        assert rest.call_args[0][0] == "repositories/ws/repo/commit/abc123/statuses"


class TestReviews:
    def test_approved_flag_wins_over_state(self):
        pr = {"participants": [{"user": {"nickname": "a"}, "approved": True, "state": None}]}
        assert bb._reviews(pr) == [c.review(author="a", state="approved")]

    def test_changes_requested_state(self):
        pr = {
            "participants": [
                {"user": {"nickname": "b"}, "approved": False, "state": "changes_requested"}
            ]
        }
        assert bb._reviews(pr)[0]["state"] == "changes_requested"

    def test_participants_with_no_verdict_are_omitted(self):
        pr = {"participants": [{"user": {"nickname": "c"}, "approved": False, "state": None}, "x"]}
        assert bb._reviews(pr) == []

    def test_no_participants_key(self):
        assert bb._reviews({}) == []

    def test_display_name_is_the_fallback_author(self):
        pr = {"participants": [{"user": {"display_name": "Full Name"}, "approved": True}]}
        assert bb._reviews(pr)[0]["author"] == "Full Name"


class TestFetchStatus:
    _PR: ClassVar[dict] = {
        "id": 3,
        "title": "Add thing",
        "author": {"nickname": "dev"},
        "state": "OPEN",
        "draft": False,
        "source": {"branch": {"name": "feat/x"}, "commit": {"hash": "cafebabe"}},
        "destination": {"branch": {"name": "main"}},
        "created_on": "c",
        "updated_on": "u",
        "links": {"html": {"href": "https://bitbucket.org/ws/repo/pull-requests/3"}},
        "participants": [],
    }

    def _run(self, pr, list_all=None):
        list_all = list_all or MagicMock(return_value=[])
        with (
            patch.object(bb, "_transport", return_value=(list_all, lambda _p: pr)),
            patch.object(bb, "_checks", return_value=[]),
        ):
            return bb.fetch_status(_TARGET, 3)

    @pytest.mark.parametrize(
        "state, expected",
        [
            ("OPEN", "open"),
            ("MERGED", "merged"),
            ("DECLINED", "closed"),
            ("SUPERSEDED", "closed"),
        ],
    )
    def test_every_state_maps_out_of_bitbucket_vocabulary(self, state, expected):
        assert self._run({**self._PR, "state": state})["state"] == expected

    def test_unknown_state_lowercases_rather_than_becoming_empty(self):
        assert self._run({**self._PR, "state": "NOVEL"})["state"] == "novel"

    def test_maps_the_envelope_fields(self):
        out = self._run(self._PR)
        assert out["head_sha"] == "cafebabe"
        assert out["source_branch"] == "feat/x" and out["target_branch"] == "main"
        assert out["author"] == "dev" and out["platform"] == "bitbucket"
        assert out["url"].endswith("/pull-requests/3")

    def test_mergeable_is_unknown_because_the_resource_exposes_none(self):
        # Guessing it from `state` would report a conflicted PR as mergeable.
        out = self._run(self._PR)
        assert out["mergeable"] is None and out["merge_state"] == ""

    def test_changed_files_come_from_diffstat(self):
        diffstat = MagicMock(
            return_value=[{"new": {"path": "a.py"}}, {"old": {"path": "b.py"}, "new": None}, "junk"]
        )
        assert self._run(self._PR, diffstat)["changed_files"] == ["a.py", "b.py"]

    def test_checks_skipped_without_a_head_sha(self):
        no_sha = {**self._PR, "source": {"branch": {"name": "x"}}}
        with (
            patch.object(
                bb, "_transport", return_value=(MagicMock(return_value=[]), lambda _p: no_sha)
            ),
            patch.object(bb, "_checks") as checks,
        ):
            assert bb.fetch_status(_TARGET, 3)["checks"] == []
        checks.assert_not_called()

    def test_secondary_failure_degrades_rather_than_losing_the_pr(self, capsys):
        def boom(_path):
            raise RuntimeError("diffstat down")

        with (
            patch.object(bb, "_transport", return_value=(boom, lambda _p: self._PR)),
            patch.object(bb, "_checks", return_value=[]),
        ):
            out = bb.fetch_status(_TARGET, 3)
        assert out["title"] == "Add thing" and out["changed_files"] == []
        assert "changed files" in capsys.readouterr().err

    def test_missing_pr_raises(self):
        with pytest.raises(c.TransportError, match="not found"):
            self._run({"type": "error"})


def test_provider_is_reachable_through_the_shared_dispatcher():
    assert c.provider_for(_TARGET) is bb
