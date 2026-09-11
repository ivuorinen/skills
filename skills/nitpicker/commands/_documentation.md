# Documentation Protocol — load before applying a fix or filing a docs finding

Trigger: about to change code, or about to file a finding whose subject is
documentation. A read-only run that files no `docs` finding never loads this.

## Docstrings are part of the fix, not a follow-up

Every module, class, and function a fix adds — or whose behavior it changes —
carries a docstring in the same change. A fix that leaves a new function
undocumented is incomplete, and an audit that lets one through has accepted the
gap. This applies to nested and private functions too: a test fake named `_boom`
still states what it simulates.

## Say why, not what

The code already states what it does; a docstring that paraphrases the body
earns nothing. Record what the reader cannot recover from the code: the failure
the function prevents, the invariant it holds, the reason a surprising line is
written that way, and the ceiling of what it does not cover. Where a defect
motivated the code, name that defect — a docstring that says "returns None when
the binary is absent, because a PostToolUse hook that raises replaces its
diagnosable message with a traceback" survives a refactor that "returns None on
failure" does not.

## Tone matches the audit voice

Declarative and specific. State limits outright rather than softening them:
"flock only, no Windows path" beats a hedge. The hedging vocabulary banned in
this repo's own skill files is banned in documentation prose too;
`.claude/rules/skill-style.md` owns that list, so it is named there and not
restated here. No compliments, no filler, no restating the function signature in
English.

## Match the file you are editing

Docstring convention, voice, and comment density are set by the surrounding
code; a fix that imports a different house style is a reformat wearing a fix's
clothes. When a repo documents a rule about its own prose, that rule outranks
this section.

## Severity when auditing

A public surface with no docstring is a `docs` finding at Low, and one whose
docstring contradicts the implementation is `docs` at Medium or higher — a wrong
docstring misleads more than an absent one.
