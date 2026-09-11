"""Tests for skills/nitpicker/scripts/pr_cli.py — the CLI driving adapter.

`pr_cli` owns everything about running as a command: which argument forms are
accepted, what goes to stdout versus stderr, and which exit code each failure
class produces. `pr_common` owns the port. The last test here pins that split,
because it is invisible at runtime — a `run_cli` moved back into `pr_common`
would keep every other test in this file green.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pr_cli as cli  # type: ignore[import-not-found]  # noqa: E402
import pr_common as c  # type: ignore[import-not-found]  # noqa: E402

# ── CLI argument forms ────────────────────────────────────────────────────────


class TestParseCliArgs:
    def test_pr_url_alone(self):
        target, number = cli.parse_cli_args(["https://gitlab.com/g/p/-/merge_requests/7"])
        assert (target.platform, target.path, number) == ("gitlab", "g/p", 7)

    def test_repo_and_number(self):
        target, number = cli.parse_cli_args(["owner/repo", "42"])
        assert (target.path, number) == ("owner/repo", 42)

    def test_legacy_owner_repo_number_form_still_accepted(self):
        target, number = cli.parse_cli_args(["owner", "repo", "42"])
        assert (target.path, number) == ("owner/repo", 42)

    def test_number_alone_reads_the_git_remote(self):
        with patch.object(c, "git_remote_url", return_value="git@github.com:o/r.git"):
            target, number = cli.parse_cli_args(["5"])
        assert (target.path, number) == ("o/r", 5)

    @pytest.mark.parametrize("argv", [["5", "--remote", "upstream"], ["--remote=upstream", "5"]])
    def test_remote_flag_selects_which_remote_is_read(self, argv):
        with patch.object(c, "git_remote_url", return_value="git@github.com:o/r.git") as remote:
            cli.parse_cli_args(argv)
        assert remote.call_args[0][0] == "upstream"

    @pytest.mark.parametrize(
        "argv", [["--platform", "gitlab", "g/p", "1"], ["--platform=gitlab", "g/p", "1"]]
    )
    def test_both_flag_spellings(self, argv):
        assert cli.parse_cli_args(argv)[0].platform == "gitlab"

    def test_flag_without_value_is_a_usage_error(self):
        with pytest.raises(c.UsageError):
            cli.parse_cli_args(["g/p", "1", "--platform"])

    def test_unknown_flag_is_not_treated_as_a_repository(self):
        # Otherwise a typo'd flag is read as a repo name and reported as a bad path.
        with pytest.raises(c.UsageError, match="unknown flag"):
            cli.parse_cli_args(["--platfrom=gitlab", "g/p", "1"])

    @pytest.mark.parametrize("argv", [[], ["a", "b", "c", "d"]])
    def test_wrong_arity(self, argv):
        with pytest.raises(c.UsageError):
            cli.parse_cli_args(argv)

    def test_custom_self_hosted_host_still_reachable_through_the_url_form(self):
        # A host no platform claims is only reachable by pasting the URL and
        # naming the platform — the adapter has to keep both halves wired.
        target, number = cli.parse_cli_args(
            ["https://git.acme.com/g/p/-/merge_requests/4", "--platform", "gitlab"]
        )
        assert (target.host, target.path, number) == ("git.acme.com", "g/p", 4)


# ── run_cli exit contract ─────────────────────────────────────────────────────


class TestRunCli:
    def test_help_prints_the_doc_and_exits_zero(self, capsys):
        assert cli.run_cli("USAGE DOC", "fetch_comments", ["--help"]) == 0
        assert "USAGE DOC" in capsys.readouterr().out

    def test_help_wins_over_a_positional_argument(self, capsys):
        # --help must never be resolved as a repository and answered with a path
        # error instead of usage text.
        assert cli.run_cli("USAGE DOC", "fetch_comments", ["owner/repo", "--help"]) == 0
        assert "USAGE DOC" in capsys.readouterr().out

    def test_usage_error_is_exit_2(self, capsys):
        assert cli.run_cli("doc", "fetch_comments", []) == 2
        assert "[error]" in capsys.readouterr().err

    def test_runtime_error_is_exit_1(self, capsys):
        provider = MagicMock()
        provider.fetch_comments.side_effect = c.TransportError("no auth")
        with patch.object(c, "provider_for", return_value=provider):
            assert cli.run_cli("doc", "fetch_comments", ["o/r", "1"]) == 1
        assert "no auth" in capsys.readouterr().err

    def test_success_prints_json_to_stdout_and_exits_zero(self, capsys):
        provider = MagicMock()
        provider.fetch_comments.return_value = {"threads": []}
        with patch.object(c, "provider_for", return_value=provider):
            assert cli.run_cli("doc", "fetch_comments", ["o/r", "1"]) == 0
        assert json.loads(capsys.readouterr().out) == {"threads": []}

    def test_dispatches_to_the_targets_platform(self):
        with patch.object(c, "provider_for") as provider_for:
            cli.run_cli("doc", "fetch_status", ["https://bitbucket.org/ws/repo/pull-requests/3"])
        assert provider_for.call_args[0][0].platform == "bitbucket"

    def test_a_usage_error_raised_by_the_provider_is_still_exit_2(self, capsys):
        # A provider can reject its input after the target parses — that is bad
        # usage, not a runtime failure, and the exit code has to say so.
        provider = MagicMock()
        provider.fetch_status.side_effect = c.UsageError("unsupported host")
        with patch.object(c, "provider_for", return_value=provider):
            assert cli.run_cli("doc", "fetch_status", ["o/r", "1"]) == 2
        assert "unsupported host" in capsys.readouterr().err


# ── the port/adapter split ────────────────────────────────────────────────────


class TestPortStaysFreeOfDeliveryConcerns:
    """`pr_common` is imported by all three providers and by `mcp_server`. None
    of them runs as this CLI, so none of them should be carrying its argv
    parsing, its stdout rendering or its exit codes."""

    @pytest.mark.parametrize("name", ["run_cli", "parse_cli_args", "_split_flags", "emit"])
    def test_cli_band_is_not_in_the_port_module(self, name):
        assert not hasattr(c, name), (
            f"pr_common.{name} is a delivery concern and belongs in pr_cli.py"
        )

    def test_the_port_does_not_import_its_driving_adapter(self):
        # The arrow points adapter -> port. A pr_common that imported pr_cli
        # would make every provider load the CLI too.
        assert "import pr_cli" not in (_SCRIPTS / "pr_common.py").read_text()

    def test_the_adapter_reaches_providers_only_through_the_port(self):
        # Importing a provider directly here would bypass platform detection and
        # re-create the dispatch pr_common.provider_for exists to own.
        source = (_SCRIPTS / "pr_cli.py").read_text()
        for provider in ("pr_github", "pr_gitlab", "pr_bitbucket"):
            assert f"import {provider}" not in source
