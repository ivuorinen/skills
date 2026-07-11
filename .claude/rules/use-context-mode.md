# Context-Mode Usage

Route every read-only or inspection command through context-mode
(`mcp__plugin_context-mode_context-mode__ctx_execute`, or `ctx_batch_execute`
for several at once): file and directory listing, `grep`, `git status`/`log`/`diff`,
test and build output, data parsing, and any command whose output you read
rather than act on. The raw output stays in the sandbox; only what you print
enters the context window.

Fetching a URL is an inspection whose body you read, so it obeys the same
rule: never reach for `WebFetch` or a raw `curl`/`wget` in Bash to pull remote
content you will read. Route it through context-mode —
`ctx_fetch_and_index` for docs/API references, or `ctx_execute` running `curl`
in the sandbox for anything else — so the fetched body stays in the sandbox and
only the extract you print enters context. The exceptions are authenticated or
private resources: `gh` for private GitHub, `WebFetch` for a `claude.ai`
artifact URL, or a token-authenticated API call such as `/nitpicker cr`'s GitHub
access (`gh`, or `curl`/`fetch` with `$GITHUB_TOKEN` when `gh` is absent) — the
`curl` fallback there is deliberate, not a violation. Route even these through
`ctx_execute` when you can, so the response body stays in the sandbox. When the
context-mode plugin is absent (a fresh clone, CI, a different agent), fall back
to `WebFetch` by discipline, exactly as the enforcement note below describes.

Append `# ctx-ok` to a plain Bash command only when context-mode cannot do the
work — a genuine state mutation whose effect must persist to the real working
tree (`git` writes, file create/delete/move, `chmod`, package install) or a
tiny fixed-output command (a literal `echo`). Tool-switching friction is never
a reason to append `# ctx-ok` to an inspection command; route it through
context-mode instead.

Enforcement of this rule is best-effort: it depends on the context-mode
plugin's PreToolUse hook being installed in the session (there is no committed
in-repo gate, and nothing validates that `# ctx-ok` marks only a mutation).
Where the plugin is absent — a fresh clone, CI, or a different agent — treat the
rule as guidance the agent applies by discipline, not a hard gate.
