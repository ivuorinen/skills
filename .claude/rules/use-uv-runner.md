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
