"""Tests for skills/nitpicker/scripts/pr_common.py and the two CLI entry points.

pr_common owns the parts every provider shares: what a git remote means, which
host a credential may be sent to, how a page is followed, and the exact shape of
the JSON the CLIs print. Those are the pieces whose breakage is silent — a
loosened host check still returns data, and a dropped envelope key still parses.
"""

import email.message
import importlib.util
import json
import runpy
import subprocess
import sys
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SCRIPTS = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pr_common as c  # type: ignore[import-not-found]  # noqa: E402

_COMMENTS_CLI = _SCRIPTS / "fetch-pr-comments.py"
_STATUS_CLI = _SCRIPTS / "fetch-pr-status.py"


def _http_resp(body, link: str = "") -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = json.dumps(body).encode()
    resp.headers.get.return_value = link
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── parse_remote_url ──────────────────────────────────────────────────────────


class TestParseRemoteUrl:
    @pytest.mark.parametrize(
        "url, expected",
        [
            ("git@github.com:owner/repo.git", ("github.com", "owner/repo")),
            ("git@github.com:owner/repo", ("github.com", "owner/repo")),
            ("https://github.com/owner/repo.git", ("github.com", "owner/repo")),
            ("https://github.com/owner/repo", ("github.com", "owner/repo")),
            ("ssh://git@github.com:22/owner/repo.git", ("github.com", "owner/repo")),
            ("https://user@bitbucket.org/ws/repo.git", ("bitbucket.org", "ws/repo")),
            ("git@gitlab.acme.com:grp/sub/proj.git", ("gitlab.acme.com", "grp/sub/proj")),
        ],
    )
    def test_supported_spellings(self, url, expected):
        assert c.parse_remote_url(url) == expected

    def test_credentials_and_port_are_not_part_of_the_host(self):
        # A netloc carrying user:pass@host:port must yield the bare host, or the
        # credential guard would pin to a string no API URL can ever match.
        assert (
            c.parse_remote_url("https://u:p@gitlab.acme.com:8443/g/p.git")[0] == "gitlab.acme.com"
        )

    @pytest.mark.parametrize("url", ["", "   ", "not-a-url", "https://github.com/"])
    def test_unparseable_raises_usage_error(self, url):
        with pytest.raises(c.UsageError):
            c.parse_remote_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "foo/bar@github.com:owner/repo",
            "a@b@c:d",
            "@github.com:owner/repo",
            "git@:owner/repo",
        ],
        ids=["slash-in-userinfo", "two-at-signs", "empty-userinfo", "empty-host"],
    )
    def test_a_malformed_scp_prefix_is_refused(self, url):
        """The scp userinfo is validated, not merely skipped over.

        When the regex here became an index split, the host was checked for `/`
        and the prefix before the last `@` was not — so
        `foo/bar@github.com:owner/repo`, which the regex refused because its
        userinfo class was `[^@/]+`, started resolving to host `github.com`.
        A malformed remote silently became a real one pointing at a host the
        user never named, which is the failure this module exists to prevent.

        The other three are stricter than the regex was: it let its *host* class
        swallow an `@` and so accepted `b@c`, `@github.com` and `git@` as
        hostnames. None can exist, so refusing them loses nothing.
        """
        with pytest.raises(c.UsageError):
            c.parse_remote_url(url)

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("github.com:org/repo@v2.git", ("github.com", "org/repo@v2")),
            ("gitlab.com:grp/my@repo.git", ("gitlab.com", "grp/my@repo")),
            ("myhost:~git@backup/repo.git", ("myhost", "~git@backup/repo")),
            ("git@github.com:org/repo@v2.git", ("github.com", "org/repo@v2")),
        ],
        ids=["at-in-path", "at-in-repo-name", "at-after-tilde", "userinfo-and-at-in-path"],
    )
    def test_an_at_sign_in_the_path_does_not_hide_the_separator(self, url, expected):
        """An `@` only opens userinfo when it precedes the first `/`.

        Taking the first `@` anywhere and searching for the separator colon
        *after* it walked past the real colon whenever the `@` was in the path:
        no colon was found, the scp branch was skipped, and a valid remote
        raised. `myhost:~git@backup/repo.git` is the case a
        first-`@`-before-the-first-slash rule still gets wrong — its `@` does
        precede the slash — so the no-userinfo reading has to stay reachable
        rather than being replaced.

        Found by a 171k-input differential sweep after two hand-written case
        sets of fourteen and eighteen spellings each reported no difference.
        """
        assert c.parse_remote_url(url) == expected

    def test_userinfo_may_still_carry_a_colon(self):
        """`user:pass@host:path` splits on the colon after the credentials.

        Pinned because the index split finds the first `:` *after* the first
        `@` precisely so the one inside the userinfo is not mistaken for the
        host/path separator.
        """
        assert c.parse_remote_url("user:pass@host:path") == ("host", "path")


# ── parse_pr_url ──────────────────────────────────────────────────────────────


class TestParsePrUrl:
    @pytest.mark.parametrize(
        "url, expected",
        [
            ("https://github.com/o/r/pull/42", ("github.com", "o/r", 42)),
            ("https://gitlab.com/g/p/-/merge_requests/7", ("gitlab.com", "g/p", 7)),
            ("https://gitlab.acme.com/g/s/p/-/merge_requests/3", ("gitlab.acme.com", "g/s/p", 3)),
            ("https://bitbucket.org/ws/repo/pull-requests/9", ("bitbucket.org", "ws/repo", 9)),
        ],
    )
    def test_each_platform_url_shape(self, url, expected):
        assert c.parse_pr_url(url) == expected

    def test_trailing_route_is_ignored(self):
        assert c.parse_pr_url("https://github.com/o/r/pull/42/files") == ("github.com", "o/r", 42)

    def test_url_without_pr_number_raises(self):
        with pytest.raises(c.UsageError):
            c.parse_pr_url("https://github.com/o/r")


# ── platform detection and target shape ───────────────────────────────────────


class TestPlatformForHost:
    @pytest.mark.parametrize(
        "host, expected",
        [
            ("github.com", "github"),
            ("gitlab.com", "gitlab"),
            ("gitlab.acme.com", "gitlab"),
            ("bitbucket.org", "bitbucket"),
            ("GitHub.com", "github"),
        ],
    )
    def test_known_hosts(self, host, expected):
        assert c.platform_for_host(host) == expected

    def test_unknown_host_refuses_rather_than_guesses(self):
        # Guessing wrong sends a credential to the wrong API, so an unrecognised
        # host is an error naming the escape hatch, never a default.
        with pytest.raises(c.UsageError, match="--platform"):
            c.platform_for_host("git.acme.internal")

    def test_override_wins_over_hostname(self):
        assert c.platform_for_host("git.acme.internal", "gitlab") == "gitlab"

    def test_unknown_override_lists_the_valid_set(self):
        with pytest.raises(c.UsageError, match="github, gitlab, bitbucket"):
            c.platform_for_host("github.com", "gitbucket")

    @pytest.mark.parametrize("host", ["..", ".", "", "-bad.com", "bad-.com", "a..b", "a/b"])
    def test_non_hostnames_refused(self, host):
        # The host becomes the netloc every credential is pinned to, so a path
        # token must never survive as one.
        with pytest.raises(c.UsageError, match="invalid host"):
            c.platform_for_host(host)

    def test_host_is_validated_before_the_override_short_circuits(self):
        # Otherwise --platform smuggles a non-hostname straight through.
        with pytest.raises(c.UsageError, match="invalid host"):
            c.platform_for_host("..", "github")


class TestTarget:
    @pytest.mark.parametrize(
        "platform, host, expected",
        [
            ("github", "github.com", "https://api.github.com"),
            ("github", "ghe.acme.com", "https://ghe.acme.com/api/v3"),
            ("gitlab", "gitlab.com", "https://gitlab.com/api/v4"),
            ("gitlab", "gitlab.acme.com", "https://gitlab.acme.com/api/v4"),
            ("bitbucket", "bitbucket.org", "https://api.bitbucket.org/2.0"),
        ],
    )
    def test_api_base(self, platform, host, expected):
        assert c.Target(platform, host, "o/r").api_base == expected

    def test_api_netloc_is_the_only_credential_destination(self):
        assert c.Target("github", "github.com", "o/r").api_netloc == "api.github.com"
        assert c.Target("gitlab", "gitlab.acme.com", "g/p").api_netloc == "gitlab.acme.com"

    def test_encoded_path_escapes_slashes_for_gitlab(self):
        assert c.Target("gitlab", "gitlab.com", "grp/sub/proj").encoded_path == "grp%2Fsub%2Fproj"


class TestResolveTarget:
    def test_bare_path_defaults_to_github(self):
        assert c.resolve_target("owner/repo") == c.Target("github", "github.com", "owner/repo")

    def test_bare_path_with_platform_uses_that_platforms_cloud_host(self):
        assert c.resolve_target("grp/proj", "gitlab").host == "gitlab.com"

    def test_host_qualified_path_is_split_on_a_recognised_platform_host(self):
        target = c.resolve_target("gitlab.acme.com/grp/proj")
        assert (target.platform, target.host, target.path) == (
            "gitlab",
            "gitlab.acme.com",
            "grp/proj",
        )

    @pytest.mark.parametrize("spec", ["my.group/sub/proj", "acme.co/team/app"])
    def test_dotted_group_name_is_a_path_not_a_host(self, spec):
        # GitLab group names legally contain dots, so "contains a dot" cannot mean
        # "is a hostname" — reading it as one aims the fetch at a host the user
        # never typed and reports a connection error naming it.
        target = c.resolve_target(spec, "gitlab")
        assert target.host == "gitlab.com"
        assert target.path == spec

    def test_only_a_claimed_hostname_counts_as_a_host(self):
        assert c._looks_like_host("gitlab.acme.com") is True
        assert c._looks_like_host("github.com") is True
        assert c._looks_like_host("bitbucket.org") is True
        # No platform claims these, so they stay part of the project path; a
        # genuinely custom host is named with the URL form instead.
        assert c._looks_like_host("my.group") is False
        assert c._looks_like_host("git.acme.com") is False

    def test_custom_self_hosted_host_still_reachable_through_the_url_form(self):
        target, number = c.parse_cli_args(
            ["https://git.acme.com/g/p/-/merge_requests/4", "--platform", "gitlab"]
        )
        assert (target.host, target.path, number) == ("git.acme.com", "g/p", 4)

    def test_gitlab_accepts_nested_groups(self):
        assert c.resolve_target("a/b/c/d", "gitlab").path == "a/b/c/d"

    @pytest.mark.parametrize("spec", ["owner/repo/extra", "owner"])
    def test_github_requires_exactly_owner_repo(self, spec):
        with pytest.raises(c.UsageError):
            c.resolve_target(spec, "github")

    @pytest.mark.parametrize(
        "spec",
        [
            "../etc/repo",
            "owner/..",
            "./repo",
            "owner/.",
            "own er/repo",
            "owner/re?po",
            "owner/re#po",
        ],
    )
    def test_traversal_and_injection_segments_rejected(self, spec):
        # These land in an API path; the charset blocks separators and the two
        # bare traversal tokens are rejected by name, since dots are legal in
        # real repository names and the charset alone would admit them.
        with pytest.raises(c.UsageError):
            c.resolve_target(spec, "github")


class TestGitRemoteUrl:
    def test_returns_the_trimmed_url(self):
        proc = MagicMock(returncode=0, stdout=b"git@github.com:o/r.git\n", stderr=b"")
        with patch.object(subprocess, "run", return_value=proc) as run:
            assert c.git_remote_url("upstream", cwd="/tmp") == "git@github.com:o/r.git"
        assert run.call_args[0][0] == ["git", "remote", "get-url", "upstream"]
        assert run.call_args[1]["cwd"] == "/tmp"

    def test_missing_remote_names_the_way_out(self):
        # The error has to say what to run instead, or the agent spends a turn
        # guessing why a repo it can see was not found.
        proc = MagicMock(returncode=2, stdout=b"", stderr=b"No such remote")
        with (
            patch.object(subprocess, "run", return_value=proc),
            pytest.raises(c.UsageError, match="owner/repo"),
        ):
            c.git_remote_url()


class TestResolveTargetFromTheWorkingTree:
    def test_resolve_target_from_remote_reads_the_git_remote(self):
        # The single remote-reading path. `resolve_target` parses specs only.
        with patch.object(c, "git_remote_url", return_value="git@gitlab.com:g/p.git"):
            assert c.resolve_target_from_remote() == c.Target("gitlab", "gitlab.com", "g/p")

    def test_resolve_target_no_longer_reads_a_remote(self):
        # Two entry points to one behaviour let a future caller pick the one that
        # silently ignores --remote; there is now exactly one.
        with patch.object(c, "git_remote_url") as remote, pytest.raises(c.UsageError):
            c.resolve_target("")
        remote.assert_not_called()

    def test_scp_style_spec_is_parsed_as_a_remote_url(self):
        assert c.resolve_target("git@bitbucket.org:ws/repo.git").platform == "bitbucket"

    def test_resolve_target_from_remote_validates_the_path(self):
        with (
            patch.object(c, "git_remote_url", return_value="git@github.com:a/b/c.git"),
            pytest.raises(c.UsageError),
        ):
            c.resolve_target_from_remote()


class TestCliHelpers:
    def test_cli_json_parses_stdout(self):
        proc = MagicMock(returncode=0, stdout=b'{"ok": 1}', stderr=b"")
        with patch.object(subprocess, "run", return_value=proc):
            assert c.cli_json(["gh", "api", "x"]) == {"ok": 1}

    def test_cli_json_treats_empty_stdout_as_no_body(self):
        proc = MagicMock(returncode=0, stdout=b"  ", stderr=b"")
        with patch.object(subprocess, "run", return_value=proc):
            assert c.cli_json(["gh", "api", "x"]) is None

    def test_cli_json_merges_concatenated_page_documents(self):
        """`glab api --paginate` emits one JSON document per page.

        Unlike `gh`, glab has no `--slurp` to wrap pages in an array, so a
        multi-page endpoint concatenates documents and a single `json.loads`
        raises — breaking the GitLab CLI fallback on exactly the large merge
        requests that need paging.
        """
        stdout = b'[{"id": 1}, {"id": 2}]\n[{"id": 3}]'
        proc = MagicMock(returncode=0, stdout=stdout, stderr=b"")
        with patch.object(subprocess, "run", return_value=proc):
            assert c.cli_json(["glab", "api", "--paginate", "x"]) == [
                {"id": 1},
                {"id": 2},
                {"id": 3},
            ]

    def test_cli_json_single_document_is_returned_unchanged(self):
        # The single-page case must not be wrapped in an extra list.
        proc = MagicMock(returncode=0, stdout=b'{"iid": 7}', stderr=b"")
        with patch.object(subprocess, "run", return_value=proc):
            assert c.cli_json(["glab", "api", "x"]) == {"iid": 7}

    def test_cli_json_keeps_non_array_pages_rather_than_dropping_them(self):
        # Concatenated objects cannot be flattened into one list; returning the
        # documents preserves every page instead of silently losing pages.
        proc = MagicMock(returncode=0, stdout=b'{"a": 1}\n{"b": 2}', stderr=b"")
        with patch.object(subprocess, "run", return_value=proc):
            assert c.cli_json(["glab", "api", "--paginate", "x"]) == [{"a": 1}, {"b": 2}]

    def test_cli_json_nonzero_raises_with_stderr(self):
        proc = MagicMock(returncode=1, stdout=b"", stderr=b"gh: not logged in")
        with (
            patch.object(subprocess, "run", return_value=proc),
            pytest.raises(c.TransportError, match="not logged in"),
        ):
            c.cli_json(["gh", "api", "x"])

    def test_cli_json_nonzero_without_stderr_still_names_the_tool(self):
        proc = MagicMock(returncode=3, stdout=b"", stderr=b"")
        with (
            patch.object(subprocess, "run", return_value=proc),
            pytest.raises(c.TransportError, match="glab exited 3"),
        ):
            c.cli_json(["glab", "api", "x"])

    def test_cli_available_true_when_the_probe_succeeds(self):
        with patch.object(subprocess, "run", return_value=MagicMock(returncode=0)):
            assert c.cli_available("gh") is True

    @pytest.mark.parametrize(
        "error",
        [
            FileNotFoundError(),
            subprocess.CalledProcessError(1, "gh"),
            subprocess.TimeoutExpired("gh", 5),
            OSError(),
        ],
    )
    def test_cli_available_false_on_every_probe_failure(self, error):
        with patch.object(subprocess, "run", side_effect=error):
            assert c.cli_available("gh") is False


class TestBestEffort:
    def test_returns_the_value_on_success(self):
        assert c.best_effort("thing", lambda: [1], []) == [1]

    def test_failure_degrades_to_the_default_and_names_itself(self, capsys):
        # A degraded result must be visibly degraded, never quietly incomplete.
        def boom():
            raise RuntimeError("rate limited")

        assert c.best_effort("checks", boom, []) == []
        err = capsys.readouterr().err
        assert "checks" in err and "rate limited" in err


class TestParsePrNumber:
    def test_valid(self):
        assert c.parse_pr_number("42") == 42

    @pytest.mark.parametrize("raw", ["not-a-number", "", "0", "-3", "4.5"])
    def test_invalid_raises_usage_error(self, raw):
        with pytest.raises(c.UsageError):
            c.parse_pr_number(raw)


# ── credential confinement ────────────────────────────────────────────────────


class TestCheckUrl:
    def test_matching_https_host_allowed(self):
        c._check_url("https://api.github.com/x", "api.github.com")

    def test_plaintext_refused_even_on_the_right_host(self):
        # A host-only check would forward the Authorization header over http://
        # to a matching hostname; both halves are required.
        with pytest.raises(c.TransportError):
            c._check_url("http://api.github.com/x", "api.github.com")

    def test_other_host_refused(self):
        with pytest.raises(c.TransportError):
            c._check_url("https://evil.example/x", "api.github.com")


# Every auth header the three providers actually send, as (name, value) pairs.
# Parametrising on this rather than on `Authorization` alone is the point: the
# handler once stripped that one name, so GitLab's PRIVATE-TOKEN survived a
# redirect off the pinned host and no test noticed. A provider added later must
# land here too — or, better, be covered for free by the allow-list the handler
# now strips against.
_PROVIDER_AUTH_HEADERS = [
    pytest.param(("Authorization", "token secret"), id="github-bitbucket"),
    pytest.param(("PRIVATE-TOKEN", "glpat-secret"), id="gitlab"),
]

# Redirect targets that must never carry a credential, and why each is unsafe.
_UNSAFE_REDIRECTS = [
    pytest.param("https://evil.example/b", id="off-host"),
    pytest.param("http://api.github.com/b", id="same-host-scheme-downgrade"),
]


class TestTokenSafeRedirectHandler:
    def _redirect(
        self,
        allowed: str,
        new_url: str,
        auth: tuple[str, str] = ("Authorization", "token secret"),
    ) -> urllib.request.Request:
        """Drive one 3xx hop through the handler carrying `auth`.

        `fp` and `headers` are typed for a live HTTP response; the base
        implementation reads neither on this path, so a stub is what the test
        can supply.

        The auth header is a parameter rather than a constant because the
        handler's job is to strip whichever one the provider chose, and pinning
        it to GitHub's spelling is what hid the GitLab leak.
        """
        req = urllib.request.Request("https://api.github.com/a", headers=dict([auth]))
        handler = c._TokenSafeRedirectHandler(allowed)
        new = handler.redirect_request(
            req,
            None,  # type: ignore[arg-type]
            302,
            "Found",
            email.message.Message(),  # type: ignore[arg-type]
            new_url,
        )
        assert new is not None
        return new

    @pytest.mark.parametrize("auth", _PROVIDER_AUTH_HEADERS)
    @pytest.mark.parametrize("new_url", _UNSAFE_REDIRECTS)
    def test_credential_stripped_on_every_unsafe_redirect(self, auth, new_url):
        """No provider's auth header survives a redirect the guard calls unsafe.

        Two independent failures, one assertion. Off-host hands the credential
        to a third party. Same-host `https` -> `http` keeps the hostname and puts
        the token on the wire in cleartext — `_check_url` refuses that URL on the
        next paginated hop, so the handler agreeing is what keeps one predicate
        from disagreeing with itself.
        """
        new = self._redirect("api.github.com", new_url, auth)
        assert not any(k.lower() == auth[0].lower() for k in new.headers)

    @pytest.mark.parametrize("auth", _PROVIDER_AUTH_HEADERS)
    def test_credential_kept_on_a_same_host_redirect(self, auth):
        """The stripping is conditional, not unconditional.

        Without this the handler could pass every test above by deleting the
        header on every hop, which would break same-host pagination instead of
        securing it.
        """
        new = self._redirect("api.github.com", "https://api.github.com/b", auth)
        assert any(k.lower() == auth[0].lower() for k in new.headers)

    def test_content_negotiation_headers_survive_an_unsafe_redirect(self):
        """Stripping by complement must not take the non-credential headers.

        `Accept` and `User-Agent` carry no secret and every provider sets them,
        so dropping them would turn a security fix into a protocol bug — the
        failure mode an allow-list invites and a deny-list does not.
        """
        req = urllib.request.Request(
            "https://api.github.com/a",
            headers={"Authorization": "token secret", "Accept": "application/json"},
        )
        handler = c._TokenSafeRedirectHandler("api.github.com")
        new = handler.redirect_request(
            req,
            None,  # type: ignore[arg-type]
            302,
            "Found",
            email.message.Message(),  # type: ignore[arg-type]
            "https://evil.example/b",
        )
        assert new is not None
        assert any(k.lower() == "accept" for k in new.headers)
        assert not any(k.lower() == "authorization" for k in new.headers)

    def test_the_handler_and_the_url_check_agree(self):
        """Both guard the same thing, so they share one predicate.

        Pinned because the bug above was not a wrong rule — it was the right
        rule written down twice and implemented once.
        """
        for url in (
            "https://api.github.com/b",
            "http://api.github.com/b",
            "https://evil.example/b",
        ):
            safe = c._credential_safe(url, "api.github.com")
            kept = any(
                k.lower() == "authorization" for k in self._redirect("api.github.com", url).headers
            )
            assert safe is kept, f"{url}: predicate says {safe}, handler says {kept}"

    def test_pinned_host_is_per_instance_not_global(self):
        # Three platforms mean three hosts; a handler pinned to one of them must
        # not silently accept another's.
        new = self._redirect("gitlab.acme.com", "https://api.github.com/b")
        assert not any(k.lower() == "authorization" for k in new.headers)


# ── pagination ────────────────────────────────────────────────────────────────


class TestPaginateLink:
    def test_single_page(self):
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = _http_resp([{"id": 1}])
            assert c.paginate_link("https://api.github.com/x", {}, "api.github.com") == [{"id": 1}]

    def test_follows_next_then_stops(self):
        pages = [
            _http_resp([{"id": 1}], '<https://api.github.com/x?page=2>; rel="next"'),
            _http_resp([{"id": 2}]),
        ]
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = pages
            out = c.paginate_link("https://api.github.com/x", {}, "api.github.com")
        assert out == [{"id": 1}, {"id": 2}]

    def test_offhost_next_is_refused_not_followed(self):
        # The Link header is server-controlled, so it is validated on every hop.
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = _http_resp(
                [{"id": 1}], '<https://evil.example/x>; rel="next"'
            )
            with pytest.raises(c.TransportError):
                c.paginate_link("https://api.github.com/x", {}, "api.github.com")

    def test_non_list_body_is_wrapped(self):
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = _http_resp({"id": 1})
            assert c.paginate_link("https://api.github.com/x", {}, "api.github.com") == [{"id": 1}]

    def test_constant_next_stops_at_the_page_cap(self, capsys):
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = _http_resp(
                [1], '<https://api.github.com/x>; rel="next"'
            )
            out = c.paginate_link("https://api.github.com/x", {}, "api.github.com")
        assert len(out) == c._MAX_PAGES
        assert "may be truncated" in capsys.readouterr().err

    def test_exhausting_pages_without_a_next_does_not_warn(self, capsys):
        # The warning must mark a genuine truncation, not a normal last page.
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = _http_resp([1])
            c.paginate_link("https://api.github.com/x", {}, "api.github.com")
        assert "may be truncated" not in capsys.readouterr().err

    def test_empty_body_contributes_nothing(self):
        resp = MagicMock()
        resp.read.return_value = b""
        resp.headers.get.return_value = ""
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = resp
            assert c.paginate_link("https://api.github.com/x", {}, "api.github.com") == []


class TestPaginateBodyNext:
    def test_follows_body_next_field(self):
        pages = [
            _http_resp({"values": [1], "next": "https://api.bitbucket.org/2.0/y"}),
            _http_resp({"values": [2]}),
        ]
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = pages
            out = c.paginate_body_next("https://api.bitbucket.org/2.0/x", {}, "api.bitbucket.org")
        assert out == [1, 2]

    def test_offhost_next_is_refused(self):
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = _http_resp(
                {"values": [1], "next": "https://evil.example/y"}
            )
            with pytest.raises(c.TransportError):
                c.paginate_body_next("https://api.bitbucket.org/2.0/x", {}, "api.bitbucket.org")

    def test_constant_next_stops_at_the_page_cap(self, capsys):
        # The `next` URL is server-chosen; a constant one used to spin forever.
        # These tools run non-interactive, so an unbounded stall is worse than an
        # error the agent can read.
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = _http_resp(
                {"values": [1], "next": "https://api.bitbucket.org/2.0/x"}
            )
            out = c.paginate_body_next("https://api.bitbucket.org/2.0/x", {}, "api.bitbucket.org")
        assert len(out) == c._MAX_PAGES
        assert "may be truncated" in capsys.readouterr().err

    def test_non_dict_body_stops_rather_than_looping(self):
        with patch.object(c.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = _http_resp([1, 2])
            assert (
                c.paginate_body_next("https://api.bitbucket.org/2.0/x", {}, "api.bitbucket.org")
                == []
            )


# ── envelope shapes ───────────────────────────────────────────────────────────


class TestEnvelopes:
    def test_comments_envelope_keys_are_stable(self):
        target = c.Target("gitlab", "gitlab.com", "g/p")
        out = c.comments_envelope(
            target, 7, threads=[], review_bodies=[], summary_comments=[], transport="token-rest"
        )
        assert set(out) == {
            "platform",
            "host",
            "repo",
            "pr_number",
            "transport",
            "threads",
            "review_bodies",
            "summary_comments",
        }
        # A platform without the concept reports it empty, never absent — a caller
        # must not have to branch on key existence to learn which platform answered.
        assert out["review_bodies"] == []

    def test_status_envelope_keys_are_stable(self):
        out = c.status_envelope(c.Target("github", "github.com", "o/r"), 1)
        assert set(out) == {
            "platform",
            "host",
            "repo",
            "pr_number",
            "url",
            "title",
            "author",
            "state",
            "is_draft",
            "source_branch",
            "target_branch",
            "head_sha",
            "created_at",
            "updated_at",
            "mergeable",
            "merge_state",
            "checks",
            "checks_summary",
            "reviews",
            "review_summary",
            "changed_files",
        }

    def test_thread_is_resolved_defaults_to_unknown_not_false(self):
        # null means "the transport could not tell"; collapsing it to False would
        # re-surface resolved threads as unresolved.
        assert c.thread(thread_id="1")["is_resolved"] is None

    def test_missing_author_becomes_unknown(self):
        assert c.comment()["author"] == "unknown"


class TestSummaries:
    def test_totals_account_for_every_check(self):
        checks = [
            c.check(name="a", status="completed", conclusion="success"),
            c.check(name="b", status="completed", conclusion="failure"),
            c.check(name="c", status="in_progress"),
            c.check(name="d", status="completed", conclusion="skipped"),
            c.check(name="e", status="completed", conclusion="timed_out"),
        ]
        summary = c.summarize_checks(checks)
        assert summary == {"total": 5, "success": 1, "failure": 2, "neutral": 1, "pending": 1}
        assert (
            summary["total"]
            == summary["success"] + summary["failure"] + summary["neutral"] + summary["pending"]
        )

    def test_review_counts(self):
        reviews = [
            c.review(author="a", state="approved"),
            c.review(author="b", state="changes_requested"),
            c.review(author="c", state="approved"),
        ]
        assert c.summarize_reviews(reviews) == {
            "approved": 2,
            "changes_requested": 1,
            "commented": 0,
        }

    def test_states_outside_the_vocabulary_are_not_counted(self):
        # A platform-specific state must not silently land in one of the buckets.
        assert c.summarize_reviews([c.review(author="a", state="dismissed")]) == {
            "approved": 0,
            "changes_requested": 0,
            "commented": 0,
        }


# ── CLI argument forms ────────────────────────────────────────────────────────


class TestParseCliArgs:
    def test_pr_url_alone(self):
        target, number = c.parse_cli_args(["https://gitlab.com/g/p/-/merge_requests/7"])
        assert (target.platform, target.path, number) == ("gitlab", "g/p", 7)

    def test_repo_and_number(self):
        target, number = c.parse_cli_args(["owner/repo", "42"])
        assert (target.path, number) == ("owner/repo", 42)

    def test_legacy_owner_repo_number_form_still_accepted(self):
        target, number = c.parse_cli_args(["owner", "repo", "42"])
        assert (target.path, number) == ("owner/repo", 42)

    def test_number_alone_reads_the_git_remote(self):
        with patch.object(c, "git_remote_url", return_value="git@github.com:o/r.git"):
            target, number = c.parse_cli_args(["5"])
        assert (target.path, number) == ("o/r", 5)

    @pytest.mark.parametrize("argv", [["5", "--remote", "upstream"], ["--remote=upstream", "5"]])
    def test_remote_flag_selects_which_remote_is_read(self, argv):
        with patch.object(c, "git_remote_url", return_value="git@github.com:o/r.git") as remote:
            c.parse_cli_args(argv)
        assert remote.call_args[0][0] == "upstream"

    @pytest.mark.parametrize(
        "argv", [["--platform", "gitlab", "g/p", "1"], ["--platform=gitlab", "g/p", "1"]]
    )
    def test_both_flag_spellings(self, argv):
        assert c.parse_cli_args(argv)[0].platform == "gitlab"

    def test_flag_without_value_is_a_usage_error(self):
        with pytest.raises(c.UsageError):
            c.parse_cli_args(["g/p", "1", "--platform"])

    def test_unknown_flag_is_not_treated_as_a_repository(self):
        # Otherwise a typo'd flag is read as a repo name and reported as a bad path.
        with pytest.raises(c.UsageError, match="unknown flag"):
            c.parse_cli_args(["--platfrom=gitlab", "g/p", "1"])

    @pytest.mark.parametrize("argv", [[], ["a", "b", "c", "d"]])
    def test_wrong_arity(self, argv):
        with pytest.raises(c.UsageError):
            c.parse_cli_args(argv)


# ── run_cli exit contract ─────────────────────────────────────────────────────


class TestRunCli:
    def test_help_prints_the_doc_and_exits_zero(self, capsys):
        assert c.run_cli("USAGE DOC", "fetch_comments", ["--help"]) == 0
        assert "USAGE DOC" in capsys.readouterr().out

    def test_help_wins_over_a_positional_argument(self, capsys):
        # --help must never be resolved as a repository and answered with a path
        # error instead of usage text.
        assert c.run_cli("USAGE DOC", "fetch_comments", ["owner/repo", "--help"]) == 0
        assert "USAGE DOC" in capsys.readouterr().out

    def test_usage_error_is_exit_2(self, capsys):
        assert c.run_cli("doc", "fetch_comments", []) == 2
        assert "[error]" in capsys.readouterr().err

    def test_runtime_error_is_exit_1(self, capsys):
        provider = MagicMock()
        provider.fetch_comments.side_effect = c.TransportError("no auth")
        with patch.object(c, "provider_for", return_value=provider):
            assert c.run_cli("doc", "fetch_comments", ["o/r", "1"]) == 1
        assert "no auth" in capsys.readouterr().err

    def test_success_prints_json_to_stdout_and_exits_zero(self, capsys):
        provider = MagicMock()
        provider.fetch_comments.return_value = {"threads": []}
        with patch.object(c, "provider_for", return_value=provider):
            assert c.run_cli("doc", "fetch_comments", ["o/r", "1"]) == 0
        assert json.loads(capsys.readouterr().out) == {"threads": []}

    def test_dispatches_to_the_targets_platform(self):
        with patch.object(c, "provider_for") as provider_for:
            c.run_cli("doc", "fetch_status", ["https://bitbucket.org/ws/repo/pull-requests/3"])
        assert provider_for.call_args[0][0].platform == "bitbucket"

    def test_a_usage_error_raised_by_the_provider_is_still_exit_2(self, capsys):
        # A provider can reject its input after the target parses — that is bad
        # usage, not a runtime failure, and the exit code has to say so.
        provider = MagicMock()
        provider.fetch_status.side_effect = c.UsageError("unsupported host")
        with patch.object(c, "provider_for", return_value=provider):
            assert c.run_cli("doc", "fetch_status", ["o/r", "1"]) == 2
        assert "unsupported host" in capsys.readouterr().err


class TestProviderFor:
    @pytest.mark.parametrize(
        "platform, module",
        [("github", "pr_github"), ("gitlab", "pr_gitlab"), ("bitbucket", "pr_bitbucket")],
    )
    def test_every_platform_resolves_to_its_provider(self, platform, module):
        provider = c.provider_for(c.Target(platform, "example.com", "a/b"))
        assert provider.__name__ == module
        # The shared contract: both operations, on every provider.
        assert callable(provider.fetch_comments) and callable(provider.fetch_status)


# ── the shipped entry points answer --help on stdout at exit 0 ────────────────


def _shipped_clis() -> list[Path]:
    """Every executable CLI under skills/*/scripts/ — discovered, not listed.

    A hard-coded list is why `findings.py` sat outside this contract: the two PR
    fetchers were pinned when they were added and nothing swept the rest.
    Library modules are excluded by the absence of a `__main__` guard, which is
    the same signal that decides whether a file is runnable at all.
    """
    root = Path(__file__).parent.parent / "skills"
    return sorted(
        p
        for p in root.glob("*/scripts/*.py")
        if '__name__ == "__main__"' in p.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("script", _shipped_clis(), ids=lambda p: p.name)
@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_every_shipped_cli_publishes_its_interface(script, flag):
    """`.claude/rules/use-uv-runner.md`: every shipped tool answers --help with
    its interface on stdout at exit 0, and documents its exit codes there.

    That is how an agent learns the tool exists, what it accepts, and — via the
    exit-code block — whether a non-zero result means "you called this wrong"
    (retry with different arguments) or "the operation failed" (report it).
    """
    # A test invoking this interpreter on a repo-local path, list argv, no shell.
    # Running the real CLI is the point: it is the only way to prove the tool
    # answers --help on stdout at exit 0, which is the contract under test.
    # nosemgrep: dangerous-subprocess-use-audit
    result = subprocess.run(
        [sys.executable, str(script), flag], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, f"{script.name} {flag} exited {result.returncode}"
    assert result.stdout.strip(), f"{script.name} printed no interface on stdout"
    assert "Exit codes:" in result.stdout, f"{script.name} does not document its exit codes"


def test_the_cli_sweep_actually_found_the_shipped_tools():
    """A discovery helper that silently matches nothing would make the contract
    above vacuous — every parametrized case would simply not exist."""
    names = {p.name for p in _shipped_clis()}
    assert {"findings.py", "fetch-pr-comments.py", "fetch-pr-status.py"} <= names
    assert "pr_common.py" not in names  # library, no __main__ guard


@pytest.mark.parametrize("script", [_COMMENTS_CLI, _STATUS_CLI])
def test_entry_points_exit_2_on_bad_usage(script):
    # Same shape as the --help case above: this interpreter, a repo-local path,
    # list argv, no shell. Marked as well as excluded in .codacy.yml because the
    # marker is proven and the exclusion is not.
    # nosemgrep: dangerous-subprocess-use-audit
    result = subprocess.run(
        [sys.executable, str(script), "a", "b", "c", "d"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert result.stdout == ""  # diagnostics go to stderr, never stdout
    assert "[error]" in result.stderr


@pytest.mark.parametrize(
    "script, operation",
    [(_COMMENTS_CLI, "fetch_comments"), (_STATUS_CLI, "fetch_status")],
)
def test_entry_points_run_as_scripts(script, operation, monkeypatch, capsys):
    """Covers each `if __name__ == '__main__'` body — the only wiring to run_cli,
    and the one place a wrong operation name would go unnoticed until a user ran
    the tool."""
    monkeypatch.setattr(sys, "argv", [str(script), "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(script), run_name="__main__")
    assert exc.value.code == 0
    assert "Usage:" in capsys.readouterr().out
    assert f'"{operation}"' in script.read_text()


@pytest.mark.parametrize("script", [_COMMENTS_CLI, _STATUS_CLI])
def test_entry_points_do_nothing_when_merely_imported(script, capsys):
    """Imported rather than run, an entry point must stay inert — the `__main__`
    guard is what keeps a tool from firing a network fetch on import."""
    spec = importlib.util.spec_from_file_location(f"probe_{script.stem}", script)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    assert capsys.readouterr().out == ""


def test_entry_points_delegate_rather_than_reimplement():
    """Both CLIs are thin. A regression that re-inlines provider logic into an
    entry point would break the one-format guarantee, so the thinness is pinned."""
    for script in (_COMMENTS_CLI, _STATUS_CLI):
        source = script.read_text()
        assert "pr_common.run_cli" in source
        assert "urllib" not in source and "subprocess" not in source
