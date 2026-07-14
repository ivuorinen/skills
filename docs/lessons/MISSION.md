# Mission: Nitpicker dispatch architecture

## Why

Understand how `/nitpicker` resolves one invocation to exactly one command —
and how the router, the shared conventions, and the individual command files
fit together — well enough to review contributions and extend the system (add
or change commands) with confidence.

## Success looks like

- Trace any `/nitpicker <text>` invocation to the exact command file that runs,
  including the alias case and the unknown-word case.
- Explain the execution order (conventions → command → execute) and why the
  router never chains commands on its own.
- Add a new command end to end: the command file plus its `SKILL.md` table row,
  and know what `validate-skill.py` enforces about both.
- Review a command-file change and catch a broken registration or a mis-scoped
  convention override.

## Constraints

- Starting from a beginner's view of the internals — lessons build from the top.
- Grounded in this repo's actual files, never general knowledge about "how CLIs
  route".

## Out of scope

- The internals of individual audit commands (what `security` or `perf` actually
  hunt). The focus is the routing/dispatch layer, not each command's own logic.
