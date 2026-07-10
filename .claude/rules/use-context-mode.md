# Context-Mode Usage

Route every read-only or inspection command through context-mode
(`mcp__plugin_context-mode_context-mode__ctx_execute`, or `ctx_batch_execute`
for several at once): file and directory listing, `grep`, `git status`/`log`/`diff`,
test and build output, data parsing, and any command whose output you read
rather than act on. The raw output stays in the sandbox; only what you print
enters the context window.

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
