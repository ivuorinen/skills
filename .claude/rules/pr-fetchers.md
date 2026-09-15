---
paths:
  - "skills/nitpicker/scripts/pr_*.py"
  - "skills/nitpicker/scripts/fetch-pr-*.py"
  - "tests/test_pr_*.py"
  - "skills/nitpicker/commands/cr.md"
---

# PR Fetchers

`cr` reads a PR's review surface through two entry points —
`fetch-pr-comments.py` and `fetch-pr-status.py` — that cover GitHub, GitLab and
Bitbucket Cloud behind **one** JSON format. Both are thin: they resolve their
sibling directory and delegate to `pr_cli.run_cli`, which parses the argument
forms and maps exceptions to the 0/1/2 exit contract.

`pr_common.py` is the **port**, and owns everything shared — git-remote parsing,
platform detection, the `Target` (platform + git host + project path, from which
the API base is derived), the credential-pinned HTTP layer, both pagination
styles, the output envelopes, and `provider_for` dispatch. One provider module
per platform (`pr_github.py`, `pr_gitlab.py`, `pr_bitbucket.py`) exposes exactly
`fetch_comments(target, n)` and `fetch_status(target, n)`.

`pr_cli.py` is the CLI **driving adapter** and is deliberately not part of that
port: argv parsing, stdout rendering and exit codes are facts about running as a
command, and `pr_common` is imported by all three providers and by
`mcp_server.py` — the other driving adapter — none of which run as this CLI.
Keeping the two apart is what lets `pr_common` stay the library its docstring
claims. `make ring-deps` prints the resulting graph.

Two invariants make the shared format worth having, and both are pinned by
tests. A field a platform cannot supply is present and empty or null rather than
absent, so a caller reads every key unconditionally instead of branching on key
existence to learn which platform answered. And a credential is only ever sent
to the host it was declared for:
the redirect handler is built per-request with that host, every paginated URL is
re-validated before it is followed (both `Link` headers and body `next` fields
are server-controlled), and a token reaches only its platform's own public
host unless `GH_HOST`/`GITLAB_HOST` names the self-hosted one. Withheld by
default, declared by exception: gating on a *mismatch* instead would let the
unconfigured case through, since it declares no host to mismatch against.
Platform detection refuses an unrecognised host rather than guessing, since a
wrong guess is a credential handed to a third party.

The MCP tools `np_pr_comments` and `np_pr_status` wrap the same providers. They
are the only tools on the server carrying `openWorldHint: true`, and their
results are wrapped in an `<untrusted-data source="pull-request">` envelope — PR
bodies are written by anyone who can comment on the PR. They are not the only
enveloped tools: `np_context_pack` and the findings readers carry their own
`source` tags, since repository paths and stored finding bodies are written by
whoever wrote the audited tree. SKILL.md's **Untrusted results** paragraph is
the full list.

## Enforcement

Both invariants are pinned by the `tests/test_pr_*.py` suites. `make ring-deps`
fails on an outward import edge; the port/adapter split inside the shipped ring
is author discipline.
