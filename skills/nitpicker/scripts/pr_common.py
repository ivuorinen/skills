#!/usr/bin/env python3
"""Shared plumbing for the PR fetchers: target resolution, HTTP, output envelopes.

Imported by `pr_github.py`, `pr_gitlab.py`, `pr_bitbucket.py` and the two CLI
entry points (`fetch-pr-comments.py`, `fetch-pr-status.py`). Stdlib-only, per
`.claude/rules/use-uv-runner.md`; it is a library, not a CLI, so it has no
`main()` and no `--help`.

The output envelopes below are the *contract*: every provider returns the same
JSON shape, so `cr` reads one format regardless of platform. A field a platform
cannot supply is present and empty/null rather than absent — a caller must never
have to branch on key existence to learn which platform produced a record.

Nothing here talks to a platform. Providers own their endpoints and auth; this
module owns what is genuinely common — parsing a git remote, pinning a token to
one host, paginating, and shaping the result.
"""

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from typing import Any

PLATFORMS = ("github", "gitlab", "bitbucket")

# One path segment of a repository/project. Deliberately the intersection of what
# the three platforms accept: it is interpolated into API paths, so it must not
# admit `/`, `?`, `@`, `#` or whitespace. Dots are legal in real names, so `.`
# and `..` are rejected by name in `_check_segments` rather than by charset.
_SEGMENT_RE = re.compile(r"[A-Za-z0-9._-]+")

# A DNS hostname: dot-separated labels of alphanumerics and hyphens, no empty
# label and no leading/trailing hyphen. Stricter than `_SEGMENT_RE` on purpose —
# this value becomes the netloc every credential is pinned to, so `..` and other
# path tokens must not survive as "hosts".
_HOST_RE = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*"
)

# How many `owner/repo`-style segments each platform's project path has. GitLab
# nests projects under arbitrarily deep groups, so it has a floor, not a count.
_MIN_SEGMENTS = {"github": 2, "gitlab": 2, "bitbucket": 2}
_MAX_SEGMENTS = {"github": 2, "gitlab": None, "bitbucket": 2}

_UA = "ivuorinen-skills/nitpicker-cr"


class UsageError(Exception):
    """Bad input from the caller — maps to exit code 2."""


class TransportError(RuntimeError):
    """A CLI or HTTP call failed. Subclasses RuntimeError so provider fallbacks
    that catch RuntimeError keep working."""


# ── target resolution ────────────────────────────────────────────────────────
class Target:
    """The repository a fetch runs against, plus the platform that hosts it.

    `host` is the *git* host (github.com, gitlab.example.com); `api_base` is the
    API origin derived from it. They differ on GitHub and Bitbucket, whose APIs
    live on a separate hostname, and coincide on GitLab, whose API is a path on
    the instance itself — which is what makes self-hosted GitLab work here at all.
    """

    def __init__(self, platform: str, host: str, path: str):
        self.platform = platform
        self.host = host
        self.path = path.strip("/")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Target(platform={self.platform!r}, host={self.host!r}, path={self.path!r})"

    def __eq__(self, other: object) -> bool:
        """Value equality on the resolved triple, so tests can compare targets.

        Defining this leaves Target unhashable — Python drops the inherited
        `__hash__` — which is fine while nothing keys a dict or set by target.
        Adding `__hash__` is the fix if that changes; widening the comparison is
        not, since two targets differing in host are different targets.
        """
        return isinstance(other, Target) and (self.platform, self.host, self.path) == (
            other.platform,
            other.host,
            other.path,
        )

    @property
    def segments(self) -> list[str]:
        return self.path.split("/")

    @property
    def api_base(self) -> str:
        """Origin every API URL for this target must start with, scheme included."""
        if self.platform == "github":
            # GitHub Enterprise Server serves its API at https://<host>/api/v3.
            # Only github.com uses the separate api. hostname.
            return (
                "https://api.github.com"
                if self.host == "github.com"
                else f"https://{self.host}/api/v3"
            )
        if self.platform == "gitlab":
            return f"https://{self.host}/api/v4"
        return "https://api.bitbucket.org/2.0"

    @property
    def api_netloc(self) -> str:
        """The only host a token for this target may ever be sent to."""
        return urllib.parse.urlsplit(self.api_base).netloc

    @property
    def encoded_path(self) -> str:
        """Project path as one URL path segment — GitLab addresses projects that way."""
        return urllib.parse.quote(self.path, safe="")


def _check_segments(platform: str, path: str) -> None:
    """Reject a project path before it is interpolated into an API URL.

    Two separate guards. The count bounds catch a path aimed at the wrong
    platform — GitHub is always owner/repo, GitLab nests arbitrarily — which
    would otherwise become a confusing 404 from a real host. The per-segment
    charset, plus the explicit `.`/`..` rejection, is what keeps a crafted path
    from walking out of the project namespace once it reaches the URL.
    """
    segments = [s for s in path.split("/") if s]
    low, high = _MIN_SEGMENTS[platform], _MAX_SEGMENTS[platform]
    if len(segments) < low or (high is not None and len(segments) > high):
        shape = "owner/repo" if high == 2 else "group[/subgroup...]/project"
        raise UsageError(f"{platform} project path must be {shape}, got {path!r}")
    for segment in segments:
        if not _SEGMENT_RE.fullmatch(segment) or segment in (".", ".."):
            raise UsageError(f"invalid path segment {segment!r} in {path!r}")


def platform_for_host(host: str, override: str = "") -> str:
    """Which platform serves `host`. `override` short-circuits the guess.

    A self-hosted instance is only recognised when its hostname says so
    (`gitlab.acme.com`) — anything else is refused rather than guessed, because
    guessing wrong sends a token to the wrong API. `--platform` is the documented
    escape hatch and is why this never has to be clever.
    """
    # Validated before the override short-circuits, so `--platform` can never
    # smuggle a non-hostname through. The host becomes the API netloc every
    # credential is pinned to, and `resolve_target` reads a dotted first segment
    # as a hostname — which made `../etc/repo` parse as host `..` with path
    # `etc/repo`, silently accepted.
    if not _HOST_RE.fullmatch(host):
        raise UsageError(f"invalid host: {host!r}")
    if override:
        if override not in PLATFORMS:
            raise UsageError(
                f"--platform must be one of {', '.join(PLATFORMS)}. Received: {override!r}"
            )
        return override
    host = host.lower()
    if host == "github.com" or host.startswith("github."):
        return "github"
    if host == "gitlab.com" or host.startswith("gitlab."):
        return "gitlab"
    if host == "bitbucket.org" or host.endswith(".bitbucket.org"):
        return "bitbucket"
    raise UsageError(
        f"cannot infer the platform of host {host!r}. "
        f"Pass --platform with one of: {', '.join(PLATFORMS)}."
    )


def parse_remote_url(url: str) -> tuple[str, str]:
    """(host, project_path) from any git remote spelling.

    Handles `git@host:path.git`, `ssh://git@host[:port]/path.git`,
    `https://host/path.git` and `https://user@host/path`.
    """
    url = url.strip()
    if not url:
        raise UsageError("empty git remote URL")
    # Scp-style (`[user@]host:path`) is split by index rather than by regex.
    # `(?:[^@/]+@)?([^/:]+):(.+)` let the optional userinfo group and the host
    # group both match a `:`, so an input had several valid splits and the engine
    # backtracked between them — the polynomial blow-up CodeQL reports as
    # py/polynomial-redos. A git remote URL is attacker-influenced wherever a
    # repository is cloned from a URL someone else chose, so this is worth not
    # having. Narrowing the character classes only reshuffles the ambiguity; the
    # fix is to stop backtracking at all.
    #
    # The host starts either right after a leading `user@`, or at position 0.
    # Those are the regex's two alternatives, and they are tried in its order —
    # greedy, so the userinfo reading first. Taking only the first `@` in the
    # whole string instead broke `github.com:org/repo@v2.git`: the `@` there is
    # in the *path*, the colon search started past it, no colon was found, and a
    # valid remote raised. An `@` only opens userinfo when it precedes the first
    # `/`, and even then the no-userinfo reading has to stay available —
    # `myhost:~git@backup/repo.git` satisfies that guard and is still hostless
    # under it.
    #
    # Each candidate host is checked for what the regex's `[^/:]+` and `[^@/]+`
    # classes enforced: non-empty, no `/`, no `@`. Rejecting `@` inside the host
    # is stricter than the regex, which accepted `a@b@c:d` as host `b@c` — not a
    # hostname that can exist.
    #
    # At most two `find` calls, and no backtracking to reason about.
    #
    # The regex this replaced was reported by CodeQL as py/polynomial-redos.
    # That finding does not survive measurement: benchmarked under `fullmatch`
    # across seven adversarial shapes at n = 2k…32k — including CodeQL's own
    # stated witness, a run of `.` — every one scaled linearly (ratio ~2.0 per
    # doubling) and stayed under 2.3 ms at 32 KB, against a known-quadratic
    # control that hit 665 ms and ratio ~4 on the same harness. Anchoring gives
    # one start position, `[^@/]+` cannot cross an `@`, and `[^/:]+` cannot
    # cross a `:`, so there is no ambiguity to compound.
    #
    # The index split therefore stands on the host reading, not on performance:
    # the regex's `[^/:]+` admitted an `@`, so it answered `a@b@c:d` with host
    # `b@c` and `@host:path` with host `@host`. Neither is a hostname. Keeping
    # the rule green is the other reason — py/polynomial-redos is not among the
    # queries `.github/codeql/codeql-config.yml` excludes.
    first_slash = url.find("/")
    limit = len(url) if first_slash == -1 else first_slash
    first_at = url.find("@")
    scp_host = scp_path = ""
    for start in ([first_at + 1] if 0 < first_at < limit else []) + [0]:
        colon = url.find(":", start)
        if colon in (-1, len(url) - 1):
            continue
        candidate = url[start:colon]
        if candidate and "/" not in candidate and "@" not in candidate:
            scp_host, scp_path = candidate, url[colon + 1 :]
            break
    if "://" not in url and scp_host:
        host, path = scp_host, scp_path
    else:
        split = urllib.parse.urlsplit(url)
        if not split.netloc:
            raise UsageError(f"unrecognised git remote URL: {url!r}")
        # netloc may carry credentials and a port; neither belongs in the host.
        host = split.netloc.rsplit("@", 1)[-1].split(":", 1)[0]
        path = split.path
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    if not host or not path:
        raise UsageError(f"unrecognised git remote URL: {url!r}")
    # Hostnames are case-insensitive, so fold here rather than at each caller:
    # every downstream comparison is an equality test against a lowercase
    # literal (`target.host == "gitlab.com"`, `== "github.com"`), and a pasted
    # `https://GitLab.COM/...` URL made all five of them miss. The visible
    # symptom was a token withheld from the platform's own public host, which
    # reads as a credential problem rather than a casing one.
    return host.lower(), path


def git_remote_url(remote: str = "origin", cwd: str | None = None) -> str:
    """The remote's URL, or a UsageError naming what to pass instead.

    Raises rather than returning empty on a missing remote: the caller's next
    step is to derive a Target from this string, and an empty one produces a
    parse failure that describes the wrong problem. The error carries git's own
    stderr plus the explicit alternatives, so a checkout with no remote — a
    tarball, a fresh CI clone — is one message away from working.
    """
    result = subprocess.run(
        ["git", "remote", "get-url", remote],
        capture_output=True,
        timeout=10,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise UsageError(
            f"no git remote {remote!r} ({result.stderr.decode().strip()}). "
            "Pass the repository explicitly, e.g. `owner/repo` or the PR URL."
        )
    return result.stdout.decode().strip()


def make_target(host: str, path: str, platform: str = "") -> Target:
    """Resolve the platform for `host` and validate `path` against it.

    The single place a Target is built. Every caller that has a host and a path
    already — the CLI's URL form, the remote reader, the MCP tools — goes through
    here rather than re-serialising to `host/path` and re-parsing, which is what
    exposed a custom self-hosted host to the ambiguity `_looks_like_host` guards.
    """
    resolved = platform_for_host(host, platform)
    _check_segments(resolved, path)
    return Target(resolved, host, path)


def _looks_like_host(segment: str) -> bool:
    """Whether a leading path segment names a platform host rather than a group.

    "Contains a dot" is not enough. GitLab group names legally contain dots, so
    `my.group/sub/proj` is a project path, not a host plus a shorter path — and
    reading it as a host aims the fetch at a hostname the user never typed. Only
    a segment some platform actually claims is treated as a host; anything else
    stays part of the project path, which is the safe default. A custom
    self-hosted host that no pattern claims is named with the URL form or read
    off the git remote.
    """
    try:
        platform_for_host(segment)
        return True
    except UsageError:
        return False


def resolve_target(spec: str, platform: str = "") -> Target:
    """Build a Target from an explicit spec.

    `spec` accepts a full web URL or SSH remote (`https://gitlab.acme.com/grp/proj`,
    `git@github.com:o/r.git`), a host-qualified path whose first segment is a
    recognised platform host (`gitlab.acme.com/grp/proj`), or a bare project path
    (`owner/repo`, `grp/sub/proj`) — the last of which carries no host, so the
    platform comes from `--platform` and defaults to github.com.

    Reading the git remote is `resolve_target_from_remote`'s job, not this one.
    """
    if "://" in spec or spec.startswith("git@"):
        host, path = parse_remote_url(spec)
    elif spec.count("/") >= 2 and _looks_like_host(spec.split("/", 1)[0]):
        host, path = spec.split("/", 1)
    else:
        # A bare path. Without a host the platform cannot be inferred, so an
        # explicit --platform decides it and github.com is the documented default.
        resolved = platform_for_host("github.com", platform)
        host = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}[
            resolved
        ]
        path = spec
    return make_target(host, path, platform)


def parse_pr_number(raw: str) -> int:
    """Parse a PR number, rejecting the values that fail late instead of here.

    Zero and negatives are refused because every platform numbers PRs from one:
    they build a well-formed URL that returns 404, which reads as a missing PR
    rather than a bad argument.
    """
    try:
        number = int(raw)
    except (TypeError, ValueError):
        raise UsageError(f"PR number must be an integer. Received: {raw!r}") from None
    if number <= 0:
        raise UsageError(f"PR number must be positive. Received: {raw!r}")
    return number


# ── HTTP ─────────────────────────────────────────────────────────────────────
def _credential_safe(url: str, allowed_netloc: str) -> bool:
    """Whether `url` may carry the caller's Authorization header.

    Both halves are the guard: the scheme, because a matching hostname reached
    over plaintext still puts the token on the wire, and the netloc, because a
    redirect elsewhere hands it to a third party.

    Shared by the redirect handler and `_check_url` deliberately. They enforced
    the same intent in two places and only one of them checked the scheme, so a
    same-host `https` -> `http` redirect kept the header while the paginator
    would have refused the identical URL. One predicate cannot disagree with
    itself that way.
    """
    split = urllib.parse.urlsplit(url)
    return split.scheme == "https" and split.netloc == allowed_netloc


# Headers that may cross an origin on a redirect. Everything else is dropped.
#
# An allow-list, not a deny-list of credential names, because a deny-list fails
# open for whatever is added after it is written — and that already happened
# here. The handler named `authorization` alone, which covers GitHub and
# Bitbucket; GitLab authenticates with `PRIVATE-TOKEN`, so a redirect off the
# pinned host forwarded a GitLab PAT intact while the docstring claimed the
# credential was stripped. Listing what is safe means the next provider's header
# is protected by default rather than by someone remembering this line exists.
#
# These three are the ones urllib or this module set for content negotiation,
# never for authentication: `_UA`, and the `Accept` each provider sends.
_SAFE_REDIRECT_HEADERS = frozenset({"user-agent", "accept", "content-type"})


class _TokenSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip every credential header on a redirect that leaves the pinned API host.

    urllib follows 3xx transparently and, unlike requests, carries the header
    across hosts — so without this a cross-host redirect forwards the token
    off-host, defeating the same-host guard in `_open`. The allowed netloc is
    per-opener rather than global: three platforms mean three different hosts,
    and a process-wide handler pinned to one of them would silently stop
    protecting the other two.
    """

    def __init__(self, allowed_netloc: str):
        super().__init__()
        self.allowed_netloc = allowed_netloc

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Keep only `_SAFE_REDIRECT_HEADERS` unless the target is still https
        on the pinned host.

        urllib copies request headers onto a redirect by default, so a server
        answering with a redirect elsewhere — or to plaintext on its own
        hostname — would be handed the credential the caller declared for this
        host. The handler is built per request with the netloc it may keep the
        header for, because a shared instance would have to be told which host
        applies on every call, and the one that forgot would leak silently.

        Strips by complement rather than by name: every provider chooses its own
        auth header (`Authorization` on GitHub and Bitbucket, `PRIVATE-TOKEN` on
        GitLab), so a name list protects whichever ones its author happened to
        know about. urllib stores header keys `.capitalize()`d, which is why the
        comparison lowercases rather than matching the spelling a caller passed.
        """
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and not _credential_safe(newurl, self.allowed_netloc):
            for key in [k for k in new.headers if k.lower() not in _SAFE_REDIRECT_HEADERS]:
                del new.headers[key]
        return new


def _check_url(url: str, allowed_netloc: str) -> None:
    """Refuse to send a token anywhere but https on the pinned host.

    Both halves matter. A host-only check still forwards Authorization over
    plaintext `http://` to a matching hostname, and every paginated URL here is
    server-controlled (a `Link` header or a `next` field in the body), so this
    runs on each hop and not only on the first.
    """
    if not _credential_safe(url, allowed_netloc):
        raise TransportError(
            f"refusing to send credentials to {url!r}; expected https://{allowed_netloc}"
        )


def http_json(
    url: str, headers: dict[str, str], allowed_netloc: str, timeout: int = 30
) -> tuple[Any, Any]:
    """GET `url` and parse JSON. Returns (body, response_headers)."""
    _check_url(url, allowed_netloc)
    opener = urllib.request.build_opener(_TokenSafeRedirectHandler(allowed_netloc))
    req = urllib.request.Request(url, headers={"User-Agent": _UA, **headers})
    # Scheme and host are pinned by _check_url immediately above, on this URL and
    # on every paginated successor before it is followed.
    with opener.open(req, timeout=timeout) as resp:  # nosec B310
        raw = resp.read()
        return (json.loads(raw) if raw else None), resp.headers


def _next_from_link(link_header: str) -> str:
    """The `rel="next"` URL from a Link header, or "" when there is no next page.

    Empty string rather than None so the paginator's loop condition stays a
    plain truth test. The returned URL is server-controlled and is re-validated
    against the pinned host before it is followed — see `_check_url`.
    """
    for part in (link_header or "").split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return ""


# Hop ceiling for both paginators. At 100 records a page that is ~10k records —
# orders of magnitude past any real PR review surface. The cap exists because the
# `next` link is chosen by the *server*: a bug, a proxy, or a hostile endpoint
# that returns a constant next URL would otherwise spin forever, and these tools
# run in non-interactive shells where an unbounded stall is worse than an error.
# The per-request timeout bounds one hop, never the loop.
_MAX_PAGES = 100


def paginate_link(url: str, headers: dict[str, str], allowed_netloc: str) -> list[Any]:
    """Follow RFC-5988 `Link: rel="next"` pagination — GitHub and GitLab both use it."""
    results: list[Any] = []
    for _ in range(_MAX_PAGES):
        body, resp_headers = http_json(url, headers, allowed_netloc)
        if isinstance(body, list):
            results.extend(body)
        elif body is not None:
            results.append(body)
        url = _next_from_link(resp_headers.get("Link", ""))
        if not url:
            return results
        # Server-controlled; validated before the next hop rather than after.
        _check_url(url, allowed_netloc)
    # Reached only by consuming every allowed hop with a `next` still pending, so
    # this is always a real truncation — no guard needed, and none that could go
    # stale into a branch that never runs.
    warn(f"stopped after {_MAX_PAGES} pages; result may be truncated")
    return results


def paginate_body_next(url: str, headers: dict[str, str], allowed_netloc: str) -> list[Any]:
    """Follow Bitbucket's `{"values": [...], "next": "<url>"}` pagination."""
    results: list[Any] = []
    for _ in range(_MAX_PAGES):
        body, _ = http_json(url, headers, allowed_netloc)
        if not isinstance(body, dict):
            return results
        results.extend(body.get("values") or [])
        url = body.get("next") or ""
        if not url:
            return results
        _check_url(url, allowed_netloc)
    warn(f"stopped after {_MAX_PAGES} pages; result may be truncated")
    return results


def cli_json(argv: list[str], timeout: int = 60) -> Any:
    """Run a platform CLI (`gh`, `glab`) and parse its JSON stdout.

    Handles a paginating CLI that emits one JSON document per page rather than
    one document overall. `gh` has `--slurp` to wrap pages in an array; `glab`
    does not, so `glab api --paginate` over a multi-page endpoint concatenates
    documents and a single `json.loads` raises — turning the GitLab CLI fallback
    into a hard failure on exactly the large merge requests that need paging.
    Consecutive documents are decoded and, when they are arrays, merged into one.
    """
    # argv is a list and no shell is involved, so there is nothing for an
    # argument to escape into. Its interpolated parts are validated upstream:
    # the host against _HOST_RE, the project path against _SEGMENT_RE with the
    # bare traversal tokens rejected by name.
    # The marker must sit on the line directly above the call — opengrep ignores
    # it even one line further up, silently.
    # nosemgrep: dangerous-subprocess-use-audit
    result = subprocess.run(argv, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        raise TransportError(
            result.stderr.decode().strip() or f"{argv[0]} exited {result.returncode}"
        )
    text = result.stdout.decode().strip()
    if not text:
        return None
    docs = _decode_concatenated(text)
    if len(docs) == 1:
        return docs[0]
    # Several pages: array pages concatenate into one list; anything else is
    # returned as the list of documents rather than silently dropping pages.
    return (
        [item for doc in docs for item in doc] if all(isinstance(d, list) for d in docs) else docs
    )


def _decode_concatenated(text: str) -> list[Any]:
    """Every JSON document in `text`, which may hold one or several back to back."""
    decoder = json.JSONDecoder()
    docs: list[Any] = []
    index = 0
    while index < len(text):
        doc, end = decoder.raw_decode(text, index)
        docs.append(doc)
        index = end
        while index < len(text) and text[index] in " \t\r\n":
            index += 1
    return docs


def cli_available(name: str) -> bool:
    """Whether `name` can actually be executed, not merely whether it is on PATH.

    Runs the tool because a broken or half-installed CLI still resolves on PATH,
    and the caller uses this to choose a transport — discovering the breakage at
    that point costs a confusing API failure instead of a clean fallback. Every
    failure mode collapses to False for the same reason: the answer feeds a
    choice between transports, and none of the distinctions change it.
    """
    try:
        # `name` is a literal tool name from this module ("gh", "glab"), never
        # caller input, and the argv is a list with no shell.
        # nosemgrep: dangerous-subprocess-use-audit
        subprocess.run([name, "--version"], capture_output=True, check=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def best_effort(label: str, fn: Callable[[], Any], default: Any) -> Any:
    """Run a secondary fetch whose failure must not discard the primary result.

    The threads/PR record is what the caller came for; a rate-limited call for
    reviews or CI checks degrades the answer but must never turn it into an error.
    Every such failure names itself on stderr, so a degraded result is visibly
    degraded rather than quietly incomplete.
    """
    try:
        return fn()
    except Exception as err:
        warn(f"could not fetch {label} ({err})")
        return default


def warn(message: str) -> None:
    """Emit a diagnostic on stderr, keeping stdout parseable as JSON.

    Every shipped tool here publishes structured data on stdout and diagnostics
    on stderr, so a caller can pipe one without the other. A warning printed to
    stdout would corrupt the payload rather than annotate it.
    """
    print(f"[warn] {message}", file=sys.stderr)


# ── output envelopes ─────────────────────────────────────────────────────────
def comment(
    *,
    # `Any`, not `str`: platforms number their comments differently (GitHub REST
    # returns an int, GraphQL an opaque node id, Bitbucket an int) and the id is
    # stringified here so a caller never has to know which.
    id: Any = "",
    author: str = "",
    body: str = "",
    created_at: str = "",
    diff_hunk: str = "",
    url: str = "",
) -> dict[str, Any]:
    """One comment in the shared shape, with every key present.

    Keyword-only and fully defaulted so a provider fills what its platform
    supplies and leaves the rest without the result changing shape. That is the
    format's central promise: a field a platform cannot supply is present and
    empty rather than absent, so a caller reads every key unconditionally
    instead of branching on key existence to infer which platform answered.
    """
    return {
        "id": str(id),
        "author": author or "unknown",
        "body": body or "",
        "created_at": created_at or "",
        "diff_hunk": diff_hunk or "",
        "url": url or "",
    }


def thread(
    *,
    thread_id: str,
    path: str = "",
    line: Any = None,
    diff_hunk: str = "",
    is_resolved: bool | None = None,
    url: str = "",
    comments: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """One inline review thread.

    `is_resolved` is tri-state on purpose: True/False when the platform reports
    it, `null` when the transport in use cannot (GitHub's REST fallback). A null
    obliges the caller to check whether the flagged code still exists rather than
    trusting the thread is live — collapsing it to False would silently re-surface
    resolved threads as unresolved.

    `line` carries the anchor where a platform reports a line but no hunk (GitLab,
    Bitbucket), so `path` is never the only anchor a caller has.
    """
    return {
        "thread_id": str(thread_id),
        "path": path or "",
        "line": line,
        "diff_hunk": diff_hunk or "",
        "is_resolved": is_resolved,
        "url": url or "",
        "comments": list(comments),
    }


def comments_envelope(
    target: Target,
    pr_number: int,
    *,
    threads: list[dict[str, Any]],
    review_bodies: list[dict[str, Any]],
    summary_comments: list[dict[str, Any]],
    transport: str,
) -> dict[str, Any]:
    """The one shape every platform's comment fetch returns.

    `review_bodies` is GitHub-only in practice: neither GitLab nor Bitbucket has
    a review-body concept, so both return it empty. It stays in the envelope
    because a caller that branched on the key's presence would be branching on
    platform, which is exactly what a shared format exists to avoid.
    """
    return {
        "platform": target.platform,
        "host": target.host,
        "repo": target.path,
        "pr_number": pr_number,
        "transport": transport,
        "threads": threads,
        "review_bodies": review_bodies,
        "summary_comments": summary_comments,
    }


def status_envelope(
    target: Target,
    pr_number: int,
    *,
    url: str = "",
    title: str = "",
    author: str = "",
    state: str = "",
    is_draft: bool = False,
    source_branch: str = "",
    target_branch: str = "",
    head_sha: str = "",
    created_at: str = "",
    updated_at: str = "",
    mergeable: bool | None = None,
    merge_state: str = "",
    checks: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    """The one shape every platform's status fetch returns.

    `state` is normalised to open/closed/merged/draft-free vocabulary
    (`open|closed|merged`), with `is_draft` carried separately — GitLab spells
    open `opened` and Bitbucket spells it `OPEN`, and a caller comparing strings
    should not have to know that. `mergeable` is tri-state: `null` means the
    platform had not finished computing it, which is not the same as "no".
    """
    checks = checks or []
    reviews = reviews or []
    return {
        "platform": target.platform,
        "host": target.host,
        "repo": target.path,
        "pr_number": pr_number,
        "url": url,
        "title": title,
        "author": author or "unknown",
        "state": state,
        "is_draft": bool(is_draft),
        "source_branch": source_branch,
        "target_branch": target_branch,
        "head_sha": head_sha,
        "created_at": created_at,
        "updated_at": updated_at,
        "mergeable": mergeable,
        "merge_state": merge_state,
        "checks": checks,
        "checks_summary": summarize_checks(checks),
        "reviews": reviews,
        "review_summary": summarize_reviews(reviews),
        "changed_files": changed_files or [],
    }


def check(*, name: str, status: str = "", conclusion: str = "", url: str = "") -> dict[str, Any]:
    """One CI check. `status` is queued|in_progress|completed; `conclusion` is
    success|failure|neutral|cancelled|skipped|"" (empty while still running)."""
    return {"name": name, "status": status, "conclusion": conclusion, "url": url}


def review(*, author: str, state: str, submitted_at: str = "") -> dict[str, Any]:
    """One review verdict. `state` is approved|changes_requested|commented."""
    return {"author": author or "unknown", "state": state, "submitted_at": submitted_at}


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, int]:
    """Counts by outcome. `pending` is anything not yet concluded, so
    total == success + failure + neutral + pending on every platform."""
    summary = {"total": len(checks), "success": 0, "failure": 0, "neutral": 0, "pending": 0}
    for item in checks:
        conclusion = (item.get("conclusion") or "").lower()
        if item.get("status") != "completed" and not conclusion:
            summary["pending"] += 1
        elif conclusion == "success":
            summary["success"] += 1
        elif conclusion in ("failure", "timed_out", "action_required", "cancelled", "error"):
            summary["failure"] += 1
        else:
            summary["neutral"] += 1
    return summary


def summarize_reviews(reviews: list[dict[str, Any]]) -> dict[str, int]:
    """Tally review verdicts into the three states every platform agrees on.

    The keys are seeded rather than accumulated, so a caller reads a count
    without checking whether that verdict occurred. A state outside the three —
    a platform-specific verdict, or one added later — is counted nowhere rather
    than raising, which keeps an unrecognised verdict from failing a fetch whose
    purpose is reporting.
    """
    summary = {"approved": 0, "changes_requested": 0, "commented": 0}
    for item in reviews:
        state = (item.get("state") or "").lower()
        if state in summary:
            summary[state] += 1
    return summary


def emit(payload: Any) -> None:
    """Structured data to stdout — the only thing that ever goes there."""
    print(json.dumps(payload, indent=2))


# ── CLI plumbing shared by both entry points ─────────────────────────────────
_PROVIDER_MODULES = {
    "github": "pr_github",
    "gitlab": "pr_gitlab",
    "bitbucket": "pr_bitbucket",
}

# The PR path segment each platform puts before the number in a web URL.
_URL_PR_RE = re.compile(r"/(?:pull|pull-requests|merge_requests)/(\d+)")


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """(host, project_path, pr_number) from a PR/MR web URL.

    Pasting the URL is what a reviewer actually has to hand, so it is accepted as
    a single argument on both CLIs. GitLab's `/-/` infix is stripped because it
    separates the project path from the route, and is not part of the path.
    """
    match = _URL_PR_RE.search(url)
    if not match:
        raise UsageError(f"no PR/MR number in URL: {url!r}")
    host, path = parse_remote_url(url[: match.start()])
    if path.endswith("/-"):
        path = path[: -len("/-")]
    return host, path, int(match.group(1))


def _split_flags(argv: list[str]) -> tuple[list[str], str, str]:
    """(positional args, --platform value, --remote value). Both spellings of a
    flag are accepted (`--platform x` and `--platform=x`), and an unknown flag is
    a usage error rather than a positional — otherwise a typo'd flag would be read
    as a repository name and reported as a bad path."""
    platform = ""
    remote = "origin"
    positional: list[str] = []
    it = iter(argv)
    for arg in it:
        if arg in ("--platform", "--remote"):
            try:
                value = next(it)
            except StopIteration:
                raise UsageError(f"{arg} needs a value") from None
            if arg == "--platform":
                platform = value
            else:
                remote = value
        elif arg.startswith("--platform="):
            platform = arg.split("=", 1)[1]
        elif arg.startswith("--remote="):
            remote = arg.split("=", 1)[1]
        elif arg.startswith("-"):
            raise UsageError(f"unknown flag: {arg!r}")
        else:
            positional.append(arg)
    return positional, platform, remote


def parse_cli_args(argv: list[str]) -> tuple[Target, int]:
    """Resolve (target, pr_number) from the argument forms both CLIs accept.

    Accepted, in the order they are tried:
        <pr-url>                          — everything comes from the URL
        <pr_number>                       — repo comes from the git remote
        <owner>/<repo> <pr_number>        — also group/sub/project, or host/owner/repo
        <owner> <repo> <pr_number>        — the 1.x GitHub form, still accepted
    Plus `--platform github|gitlab|bitbucket` and `--remote <name>` anywhere.
    """
    positional, platform, remote = _split_flags(argv)

    if len(positional) == 1 and _URL_PR_RE.search(positional[0]):
        host, path, number = parse_pr_url(positional[0])
        return make_target(host, path, platform), number
    if len(positional) == 1:
        return resolve_target_from_remote(platform, remote), parse_pr_number(positional[0])
    if len(positional) == 2:
        return resolve_target(positional[0], platform), parse_pr_number(positional[1])
    if len(positional) == 3:
        return (
            resolve_target(f"{positional[0]}/{positional[1]}", platform),
            parse_pr_number(positional[2]),
        )
    raise UsageError(
        "expected a PR URL, a PR number, or <repo> <pr_number>. "
        "Run with --help for the accepted forms."
    )


def resolve_target_from_remote(platform: str = "", remote: str = "origin") -> Target:
    """The only path that reads a git remote. `resolve_target` parses specs."""
    host, path = parse_remote_url(git_remote_url(remote))
    return make_target(host, path, platform)


def provider_for(target: Target) -> Any:
    """The provider module that serves `target`'s platform.

    Imported on demand rather than at module load: every provider imports this
    module, so a top-level import here would be a cycle.
    """
    import importlib

    # The imported name is never attacker-influenced: it is one of the three
    # literal values in _PROVIDER_MODULES, keyed by a platform that
    # platform_for_host already refused to guess at. Any other value raises
    # KeyError here rather than reaching importlib.
    # The marker must sit on the line directly above the call — opengrep ignores
    # it even one line further up, silently.
    # nosemgrep: non-literal-import
    return importlib.import_module(_PROVIDER_MODULES[target.platform])


def run_cli(doc: str, operation: str, argv: list[str]) -> int:
    """Shared main() for both entry points. Returns the process exit code.

    Both CLIs differ only in which provider function they call, so the argument
    parsing, `--help` handling, provider dispatch and exit-code mapping live here
    once. Exit codes: 0 success, 1 runtime/API error, 2 usage error — the contract
    every shipped tool in this repo publishes.

    `--help` is handled before any argument is resolved as a repository, so the
    flag never gets read as input and answered with a path error instead of usage.
    """
    if "--help" in argv or "-h" in argv:
        print(doc)
        return 0
    try:
        target, pr_number = parse_cli_args(argv)
    except UsageError as err:
        print(f"[error] {err}", file=sys.stderr)
        return 2
    try:
        emit(getattr(provider_for(target), operation)(target, pr_number))
    except UsageError as err:
        print(f"[error] {err}", file=sys.stderr)
        return 2
    except Exception as err:
        print(f"[error] {err}", file=sys.stderr)
        return 1
    return 0
