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
    scp = re.fullmatch(r"(?:[^@/]+@)?([^/:]+):(.+)", url)
    if scp and "://" not in url:
        host, path = scp.group(1), scp.group(2)
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
    return host, path


def git_remote_url(remote: str = "origin", cwd: str | None = None) -> str:
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


def resolve_target(spec: str = "", platform: str = "", cwd: str | None = None) -> Target:
    """Build a Target from an explicit spec, or from the repo's `origin` remote.

    `spec` accepts a full web URL (`https://gitlab.acme.com/grp/proj`), a
    host-qualified path (`gitlab.acme.com/grp/proj`), or a bare project path
    (`owner/repo`) — the last of which carries no host, so the platform must come
    from `--platform` or default to github.com.
    """
    if not spec:
        host, path = parse_remote_url(git_remote_url(cwd=cwd))
    elif "://" in spec or spec.startswith("git@"):
        host, path = parse_remote_url(spec)
    elif "." in spec.split("/", 1)[0] and spec.count("/") >= 2:
        # `host/owner/repo` — a dotted first segment is a hostname, not an owner.
        host, path = spec.split("/", 1)
    else:
        # A bare path. Without a host the platform cannot be inferred, so an
        # explicit --platform decides it and github.com is the documented default.
        resolved = platform_for_host("github.com", platform)
        host = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}[
            resolved
        ]
        path = spec
    resolved = platform_for_host(host, platform)
    _check_segments(resolved, path)
    return Target(resolved, host, path)


def parse_pr_number(raw: str) -> int:
    try:
        number = int(raw)
    except (TypeError, ValueError):
        raise UsageError(f"PR number must be an integer. Received: {raw!r}") from None
    if number <= 0:
        raise UsageError(f"PR number must be positive. Received: {raw!r}")
    return number


# ── HTTP ─────────────────────────────────────────────────────────────────────
class _TokenSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip Authorization on a redirect that leaves the pinned API host.

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
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != self.allowed_netloc:
            for key in [k for k in new.headers if k.lower() == "authorization"]:
                del new.headers[key]
        return new


def _check_url(url: str, allowed_netloc: str) -> None:
    """Refuse to send a token anywhere but https on the pinned host.

    Both halves matter. A host-only check still forwards Authorization over
    plaintext `http://` to a matching hostname, and every paginated URL here is
    server-controlled (a `Link` header or a `next` field in the body), so this
    runs on each hop and not only on the first.
    """
    split = urllib.parse.urlsplit(url)
    if split.scheme != "https" or split.netloc != allowed_netloc:
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
    for part in (link_header or "").split(","):
        if 'rel="next"' in part:
            return part.split(";")[0].strip().strip("<>")
    return ""


def paginate_link(url: str, headers: dict[str, str], allowed_netloc: str) -> list[Any]:
    """Follow RFC-5988 `Link: rel="next"` pagination — GitHub and GitLab both use it."""
    results: list[Any] = []
    while url:
        body, resp_headers = http_json(url, headers, allowed_netloc)
        if isinstance(body, list):
            results.extend(body)
        elif body is not None:
            results.append(body)
        url = _next_from_link(resp_headers.get("Link", ""))
        if url:
            # Server-controlled; validated before the next hop rather than after.
            _check_url(url, allowed_netloc)
    return results


def paginate_body_next(url: str, headers: dict[str, str], allowed_netloc: str) -> list[Any]:
    """Follow Bitbucket's `{"values": [...], "next": "<url>"}` pagination."""
    results: list[Any] = []
    while url:
        body, _ = http_json(url, headers, allowed_netloc)
        if not isinstance(body, dict):
            break
        results.extend(body.get("values") or [])
        url = body.get("next") or ""
        if url:
            _check_url(url, allowed_netloc)
    return results


def cli_json(argv: list[str], timeout: int = 60) -> Any:
    """Run a platform CLI (`gh`, `glab`) and parse its JSON stdout."""
    result = subprocess.run(argv, capture_output=True, timeout=timeout)
    if result.returncode != 0:
        raise TransportError(
            result.stderr.decode().strip() or f"{argv[0]} exited {result.returncode}"
        )
    return json.loads(result.stdout) if result.stdout.strip() else None


def cli_available(name: str) -> bool:
    try:
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
        resolved = platform_for_host(host, platform)
        _check_segments(resolved, path)
        return Target(resolved, host, path), number
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
    host, path = parse_remote_url(git_remote_url(remote))
    resolved = platform_for_host(host, platform)
    _check_segments(resolved, path)
    return Target(resolved, host, path)


def provider_for(target: Target) -> Any:
    """The provider module that serves `target`'s platform.

    Imported on demand rather than at module load: every provider imports this
    module, so a top-level import here would be a cycle.
    """
    import importlib

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
