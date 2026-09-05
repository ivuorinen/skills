"""Tests for skills/nitpicker/scripts/pr_gitlab.py.

The provider's job is to make GitLab's vocabulary disappear: discussions become
threads or summary comments, `opened` becomes `open`, pipeline jobs become
checks. Those mappings are where a caller silently gets the wrong answer, so each
is pinned here rather than inferred from the endpoint call.
"""

import sys
from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pr_common as c  # type: ignore[import-not-found]  # noqa: E402
import pr_gitlab as gl  # type: ignore[import-not-found]  # noqa: E402

_TARGET = c.Target("gitlab", "gitlab.com", "grp/proj")
_SELF_HOSTED = c.Target("gitlab", "gitlab.acme.com", "grp/sub/proj")


def _note(note_id=1, body="fix", position=None, system=False, resolvable=False, resolved=False):
    return {
        "id": note_id,
        "body": body,
        "author": {"username": "reviewer"},
        "created_at": "2024-01-01",
        "updated_at": "2024-01-02",
        "system": system,
        "resolvable": resolvable,
        "resolved": resolved,
        **({"position": position} if position else {}),
    }


# ── credential confinement ────────────────────────────────────────────────────


class TestTokenHostGuard:
    """A gitlab.com token must never be forwarded to whatever self-hosted host the
    git remote happened to name — that is a credential leak, not a failed call."""

    def test_token_withheld_from_an_undeclared_self_hosted_host(self, monkeypatch, capsys):
        monkeypatch.setenv("GITLAB_TOKEN", "tok")
        monkeypatch.delenv("GITLAB_HOST", raising=False)
        assert gl._token_for(_SELF_HOSTED) == ""
        assert "not declared for gitlab.acme.com" in capsys.readouterr().err

    def test_token_used_for_gitlab_com_without_a_declaration(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "tok")
        monkeypatch.delenv("GITLAB_HOST", raising=False)
        assert gl._token_for(_TARGET) == "tok"

    def test_token_used_when_the_declared_host_matches(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "tok")
        monkeypatch.setenv("GITLAB_HOST", "GitLab.ACME.com")
        assert gl._token_for(_SELF_HOSTED) == "tok"

    def test_token_accepts_a_declared_host_written_as_a_url(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "tok")
        monkeypatch.setenv("GITLAB_HOST", "https://gitlab.acme.com")
        assert gl._token_for(_SELF_HOSTED) == "tok"

    def test_token_withheld_when_the_declared_host_differs(self, monkeypatch, capsys):
        monkeypatch.setenv("GITLAB_TOKEN", "tok")
        monkeypatch.setenv("GITLAB_HOST", "gitlab.com")
        assert gl._token_for(_SELF_HOSTED) == ""
        assert "not sending it" in capsys.readouterr().err

    def test_absent_token_stays_absent(self, monkeypatch):
        monkeypatch.delenv("GITLAB_TOKEN", raising=False)
        monkeypatch.setenv("GITLAB_HOST", "gitlab.com")
        assert gl._token_for(_TARGET) == ""

    def test_blank_declared_host_is_not_a_declaration(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "tok")
        monkeypatch.setenv("GITLAB_HOST", "   ")
        assert gl._token_for(_SELF_HOSTED) == ""


class TestTransport:
    def test_token_rest_is_preferred_and_pins_the_instance_host(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "tok")
        monkeypatch.setenv("GITLAB_HOST", "gitlab.acme.com")
        rest_list, rest_get, label = gl._transport(_SELF_HOSTED)
        assert label == "token-rest"
        with patch.object(c, "paginate_link", return_value=[]) as paginate:
            rest_list("projects/x/merge_requests/1/discussions")
        assert paginate.call_args[0][0].startswith("https://gitlab.acme.com/api/v4/")
        assert paginate.call_args[0][1]["PRIVATE-TOKEN"] == "tok"
        assert paginate.call_args[0][2] == "gitlab.acme.com"
        with patch.object(c, "http_json", return_value=({"iid": 1}, {})):
            assert rest_get("projects/x/merge_requests/1") == {"iid": 1}

    def test_per_page_joins_an_existing_query_string_with_ampersand(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "tok")
        monkeypatch.delenv("GITLAB_HOST", raising=False)
        rest_list, _get, _label = gl._transport(_TARGET)
        with patch.object(c, "paginate_link", return_value=[]) as paginate:
            rest_list("projects/x/pipelines?scope=finished")
        assert "?scope=finished&per_page=100" in paginate.call_args[0][0]

    def test_glab_used_when_no_token(self, monkeypatch):
        monkeypatch.delenv("GITLAB_TOKEN", raising=False)
        with patch.object(c, "cli_available", return_value=True):
            list_all, get_one, label = gl._transport(_SELF_HOSTED)
        assert label == "glab"
        with patch.object(c, "cli_json", return_value=[{"id": 1}]) as cli:
            assert list_all("projects/x/y") == [{"id": 1}]
        assert cli.call_args[0][0][:4] == ["glab", "api", "--hostname", "gitlab.acme.com"]
        with patch.object(c, "cli_json", return_value={"iid": 2}):
            assert get_one("projects/x") == {"iid": 2}

    @pytest.mark.parametrize("result, expected", [(None, []), ({"id": 1}, [{"id": 1}])])
    def test_glab_non_list_results_are_normalised(self, result, expected, monkeypatch):
        monkeypatch.delenv("GITLAB_TOKEN", raising=False)
        with patch.object(c, "cli_available", return_value=True):
            list_all, _get, _label = gl._transport(_TARGET)
        with patch.object(c, "cli_json", return_value=result):
            assert list_all("projects/x/y") == expected

    def test_no_auth_names_both_options(self, monkeypatch):
        monkeypatch.delenv("GITLAB_TOKEN", raising=False)
        with (
            patch.object(c, "cli_available", return_value=False),
            pytest.raises(c.TransportError, match="GITLAB_TOKEN"),
        ):
            gl._transport(_TARGET)


# ── discussions -> threads + summary comments ─────────────────────────────────


class TestSplitDiscussions:
    def test_positioned_discussion_becomes_a_thread(self):
        position = {"new_path": "src/f.py", "new_line": 12, "old_path": "src/f.py"}
        discussions = [
            {"id": "abc", "notes": [_note(position=position, resolvable=True, resolved=False)]}
        ]
        threads, summary = gl._split_discussions(_TARGET, 7, discussions)
        assert summary == []
        assert threads[0]["thread_id"] == "abc"
        assert threads[0]["path"] == "src/f.py"
        assert threads[0]["line"] == 12
        assert threads[0]["is_resolved"] is False
        # GitLab reports a position, not a hunk; `line` is the anchor instead.
        assert threads[0]["diff_hunk"] == ""
        assert threads[0]["url"].endswith("/-/merge_requests/7#note_1")

    def test_resolved_flag_is_read_from_the_resolvable_note(self):
        position = {"new_path": "f.py", "new_line": 1}
        discussions = [
            {"id": "abc", "notes": [_note(position=position, resolvable=True, resolved=True)]}
        ]
        threads, _ = gl._split_discussions(_TARGET, 7, discussions)
        assert threads[0]["is_resolved"] is True

    def test_thread_without_a_resolvable_note_reports_unknown(self):
        position = {"new_path": "f.py", "new_line": 1}
        discussions = [{"id": "abc", "notes": [_note(position=position)]}]
        threads, _ = gl._split_discussions(_TARGET, 7, discussions)
        assert threads[0]["is_resolved"] is None

    def test_old_path_and_line_used_when_the_anchor_is_a_deleted_line(self):
        position = {"old_path": "gone.py", "old_line": 4, "new_path": None, "new_line": None}
        discussions = [{"id": "abc", "notes": [_note(position=position)]}]
        threads, _ = gl._split_discussions(_TARGET, 7, discussions)
        assert threads[0]["path"] == "gone.py" and threads[0]["line"] == 4

    def test_unpositioned_discussion_becomes_summary_comments(self):
        discussions = [{"id": "d1", "notes": [_note(body="please rebase")]}]
        threads, summary = gl._split_discussions(_TARGET, 7, discussions)
        assert threads == []
        assert summary == [
            {
                "author": "reviewer",
                "created_at": "2024-01-01",
                "updated_at": "2024-01-02",
                "body": "please rebase",
            }
        ]

    def test_system_notes_are_dropped(self):
        # "added 3 commits" is an activity record, never review feedback.
        discussions = [{"id": "d1", "notes": [_note(body="added 3 commits", system=True)]}]
        assert gl._split_discussions(_TARGET, 7, discussions) == ([], [])

    def test_blank_bodied_notes_are_not_summary_comments(self):
        discussions = [{"id": "d1", "notes": [_note(body="   ")]}]
        assert gl._split_discussions(_TARGET, 7, discussions) == ([], [])

    def test_replies_stay_in_one_thread(self):
        position = {"new_path": "f.py", "new_line": 2}
        discussions = [
            {
                "id": "abc",
                "notes": [_note(1, position=position), _note(2, body="done"), _note(3, body="ok")],
            }
        ]
        threads, _ = gl._split_discussions(_TARGET, 7, discussions)
        assert len(threads) == 1
        assert [x["id"] for x in threads[0]["comments"]] == ["1", "2", "3"]

    def test_malformed_entries_are_skipped(self):
        assert gl._split_discussions(
            _TARGET, 7, ["junk", {"id": "d"}, {"id": "e", "notes": []}]
        ) == (
            [],
            [],
        )

    def test_missing_author_becomes_unknown(self):
        discussions = [{"id": "d1", "notes": [{"id": 1, "body": "x", "author": None}]}]
        _threads, summary = gl._split_discussions(_TARGET, 7, discussions)
        assert summary[0]["author"] == "unknown"


class TestFetchComments:
    def test_envelope_reports_the_platform_and_empty_review_bodies(self, monkeypatch):
        monkeypatch.setenv("GITLAB_TOKEN", "tok")
        monkeypatch.delenv("GITLAB_HOST", raising=False)
        with patch.object(gl, "_transport", return_value=(MagicMock(return_value=[]), None, "x")):
            out = gl.fetch_comments(_TARGET, 7)
        assert out["platform"] == "gitlab" and out["repo"] == "grp/proj"
        # GitLab has no review-body concept — reported empty, never absent.
        assert out["review_bodies"] == []
        assert out["transport"] == "x"

    def test_calls_the_discussions_endpoint(self):
        rest = MagicMock(return_value=[])
        with patch.object(gl, "_transport", return_value=(rest, None, "x")):
            gl.fetch_comments(_SELF_HOSTED, 7)
        assert rest.call_args[0][0] == "projects/grp%2Fsub%2Fproj/merge_requests/7/discussions"


# ── status ────────────────────────────────────────────────────────────────────


class TestChecks:
    def test_head_pipeline_jobs_become_checks(self):
        def rest(path):
            if path.endswith("/pipelines"):
                return [{"id": 99}, {"id": 98}]
            return [
                {"name": "build", "status": "success", "web_url": "u"},
                {"name": "test", "status": "running", "web_url": "v"},
            ]

        checks = gl._checks(_TARGET, 7, rest)
        assert [x["name"] for x in checks] == ["build", "test"]
        assert checks[0]["status"] == "completed" and checks[0]["conclusion"] == "success"
        assert checks[1]["status"] == "in_progress" and checks[1]["conclusion"] == ""

    def test_newest_pipeline_is_the_one_read(self):
        seen = {}

        def rest(path):
            if path.endswith("/pipelines"):
                return [{"id": 99}, {"id": 98}]
            seen["path"] = path
            return []

        gl._checks(_TARGET, 7, rest)
        assert "/pipelines/99/jobs" in seen["path"]

    def test_no_pipeline_yields_no_checks(self):
        assert gl._checks(_TARGET, 7, lambda _p: []) == []

    @pytest.mark.parametrize(
        "status, expected",
        [
            ("failed", ("completed", "failure")),
            ("canceled", ("completed", "cancelled")),
            ("skipped", ("completed", "skipped")),
            ("manual", ("completed", "neutral")),
            ("pending", ("queued", "")),
            ("something-new", ("in_progress", "")),
        ],
    )
    def test_every_job_status_maps(self, status, expected):
        def rest(path):
            return [{"id": 1}] if path.endswith("/pipelines") else [{"name": "j", "status": status}]

        check = gl._checks(_TARGET, 7, rest)[0]
        assert (check["status"], check["conclusion"]) == expected

    def test_non_dict_jobs_are_skipped(self):
        def rest(path):
            return [{"id": 1}] if path.endswith("/pipelines") else ["junk"]

        assert gl._checks(_TARGET, 7, rest) == []


class TestReviews:
    def test_approvals_become_approved_verdicts(self):
        approvals = {"approved_by": [{"user": {"username": "alice"}}]}
        reviews = gl._reviews({}, _TARGET, 7, lambda _p: approvals)
        assert reviews == [c.review(author="alice", state="approved")]

    def test_requested_changes_read_from_the_mrs_reviewers(self):
        mr = {"reviewers": [{"username": "bob", "state": "requested_changes"}]}
        reviews = gl._reviews(mr, _TARGET, 7, lambda _p: {})
        assert reviews == [c.review(author="bob", state="changes_requested")]

    def test_approval_supersedes_an_earlier_change_request(self):
        mr = {"reviewers": [{"username": "bob", "state": "requested_changes"}]}
        approvals = {"approved_by": [{"user": {"username": "bob"}}]}
        reviews = gl._reviews(mr, _TARGET, 7, lambda _p: approvals)
        assert reviews == [c.review(author="bob", state="approved")]

    def test_other_reviewer_states_carry_no_verdict(self):
        mr = {"reviewers": [{"username": "bob", "state": "unreviewed"}, "junk"]}
        assert gl._reviews(mr, _TARGET, 7, lambda _p: {}) == []

    def test_missing_usernames_become_unknown(self):
        approvals = {"approved_by": [{}, None]}
        assert [r["author"] for r in gl._reviews({}, _TARGET, 7, lambda _p: approvals)] == [
            "unknown"
        ]

    def test_approvals_failure_degrades_without_losing_the_reviewers(self, capsys):
        mr = {"reviewers": [{"username": "bob", "state": "requested_changes"}]}

        def boom(_path):
            raise RuntimeError("approvals down")

        assert gl._reviews(mr, _TARGET, 7, boom)[0]["state"] == "changes_requested"
        assert "approvals" in capsys.readouterr().err

    def test_null_approvals_body_is_tolerated(self):
        assert gl._reviews({}, _TARGET, 7, lambda _p: None) == []


class TestMergeable:
    @pytest.mark.parametrize("detailed", ["checking", "unchecked", ""])
    def test_undecided_is_null_not_false(self, detailed):
        # Collapsing "not decided yet" to False reports a fine MR as blocked.
        assert gl._mergeable(detailed) is None

    def test_mergeable(self):
        assert gl._mergeable("mergeable") is True

    def test_blocked(self):
        assert gl._mergeable("discussions_not_resolved") is False


class TestFetchStatus:
    _MR: ClassVar[dict] = {
        "iid": 7,
        "web_url": "https://gitlab.com/grp/proj/-/merge_requests/7",
        "title": "Add thing",
        "author": {"username": "dev"},
        "state": "opened",
        "draft": False,
        "source_branch": "feat/x",
        "target_branch": "main",
        "sha": "cafebabe",
        "created_at": "c",
        "updated_at": "u",
        "detailed_merge_status": "mergeable",
    }

    def _run(self, mr, rest_list=None):
        rest_list = rest_list or MagicMock(return_value=[])
        with (
            patch.object(gl, "_transport", return_value=(rest_list, lambda _p: mr, "token-rest")),
            patch.object(gl, "_checks", return_value=[]),
            patch.object(gl, "_reviews", return_value=[]),
        ):
            return gl.fetch_status(_TARGET, 7)

    def test_state_is_normalised_out_of_gitlab_vocabulary(self):
        assert self._run(self._MR)["state"] == "open"

    @pytest.mark.parametrize(
        "gitlab_state, expected",
        [("opened", "open"), ("locked", "open"), ("closed", "closed"), ("merged", "merged")],
    )
    def test_every_state_maps(self, gitlab_state, expected):
        assert self._run({**self._MR, "state": gitlab_state})["state"] == expected

    def test_unknown_state_passes_through_rather_than_becoming_empty(self):
        assert self._run({**self._MR, "state": "novel"})["state"] == "novel"

    def test_legacy_work_in_progress_flag_still_marks_a_draft(self):
        assert self._run({**self._MR, "draft": False, "work_in_progress": True})["is_draft"] is True

    def test_maps_the_remaining_envelope_fields(self):
        out = self._run(self._MR)
        assert out["head_sha"] == "cafebabe"
        assert out["source_branch"] == "feat/x" and out["target_branch"] == "main"
        assert out["mergeable"] is True and out["merge_state"] == "mergeable"
        assert out["author"] == "dev" and out["platform"] == "gitlab"

    def test_changed_files_come_from_the_diffs_endpoint(self):
        rest = MagicMock(return_value=[{"new_path": "a.py"}, {"old_path": "b.py"}, "junk"])
        assert self._run(self._MR, rest)["changed_files"] == ["a.py", "b.py"]

    def test_missing_mr_raises(self):
        with pytest.raises(c.TransportError, match="not found"):
            self._run({"message": "404 Not found"})


def test_provider_is_reachable_through_the_shared_dispatcher():
    assert c.provider_for(_TARGET) is gl
