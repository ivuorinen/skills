# graphify

This project has a knowledge graph at `graphify-out/` with god nodes, community
structure, and cross-file relationships. The rules below were written into
`CLAUDE.md` by `graphify claude install` and moved here, where installed
behavioural rules belong.

- For codebase questions, first run `graphify query "<question>"` when `graphify-out/graph.json` exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than `graphify-out/GRAPH_REPORT.md` or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

Re-running `graphify claude install` writes the `## graphify` section back into
`CLAUDE.md`. Delete it there again; this file is its home.

## Enforcement

Partly gated. When graphify is installed, the `graphify hook-guard` PreToolUse
guards (`.claude/rules/hook-inventory.md`) remind before a raw read or search;
running `graphify update .` after an edit is agent discipline, and nothing
checks it.
