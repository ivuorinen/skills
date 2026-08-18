# Script Execution

Two script classes with different runners — never mix them up:

**Internal dev tooling** (`scripts/`, `scripts/hooks/`, `tests/` — validation,
release, hooks; never shipped to skill consumers): invoke with
`uv run --quiet <script>`, never `python3 <script>`. New internal scripts
must begin with `#!/usr/bin/env -S uv run --quiet` and include the
`# /// script` inline metadata block.

**Shipped skill tools** (anything under `skills/*/scripts/` — bundled with
the skill and executed on consumer machines): must be stdlib-only, run with
plain `python3 <script>`, and begin with `#!/usr/bin/env python3`. No
`# /// script` block, no uv invocation, no imports outside the standard
library — uv cannot be assumed to exist on systems running the skills.

`scripts/check-stdlib-only.py` gates the stdlib half in pre-commit and CI. The
runner split itself is author discipline.

## Designing a shipped tool for agentic use

An agent reads a script's stdout and stderr to decide what to do next
(<https://agentskills.io/skill-creation/using-scripts>). Every shipped tool
therefore:

- **Answers `--help` and `-h`** with its interface, on stdout, exit 0. This is
  how an agent learns the tool exists and what it accepts. Handle the flag
  before any positional argument is resolved as a path, or `--help` gets read
  as input and the agent receives a path error instead of usage text.
- **Never prompts.** Agents run in non-interactive shells; a TTY prompt hangs
  the run forever. Take every input as a flag, an environment variable, or
  stdin.
- **Separates data from diagnostics.** Structured data (JSON) on stdout,
  progress and errors on stderr, so the agent pipes clean output while keeping
  the diagnostics readable.
- **Uses distinct exit codes** per failure class, documented in `--help`. The
  bundled tools use 0 = success, 1 = runtime/IO error, 2 = usage error.
- **Fails loudly on bad input.** A missing file exits non-zero. Emitting an
  empty-but-valid result with exit 0 reads to the agent as "nothing found"
  rather than "the input was wrong".
- **Bounds its output.** Agent harnesses truncate long tool output. Summarize
  by default and expose a flag for the full set.

Error text shapes the agent's next attempt: say what was received, what was
expected, and what to run instead. `Error: --format must be one of json, csv,
table. Received: "xml"` costs one turn; `Error: invalid input` costs several.
